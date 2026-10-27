from __future__ import annotations

import sys
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
sys.path.insert(0, str(DATA_DIR))

import ingest_documents  # noqa: E402

from app.database.base import Base
from app.database.models import Organization, SourceDocument

ORG_ID = uuid4()


@pytest.fixture
def session_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Organization.__table__, SourceDocument.__table__])
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture
def session(session_factory) -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def make_filing(**overrides):
    filing = {
        "ticker": "AAPL",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "cik": "0000320193",
        "accession_number": "0000320193-24-000123",
        "primary_document": "aapl-20240928.htm",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
        "local_path": "2024/aapl_10-k_2024-11-01_0000320193-24-000123.htm",
    }
    filing.update(overrides)
    return filing


def write_markdown(markdown_dir: Path, filing: dict, content: str) -> None:
    md_path = markdown_dir / Path(filing["local_path"]).with_suffix(".md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(content, encoding="utf-8")


def test_document_title_formats_ticker_form_and_date():
    filing = make_filing()
    assert ingest_documents.document_title(filing) == "AAPL 10-K 2024-09-28"


def test_document_title_falls_back_to_filing_date_when_report_date_missing():
    filing = make_filing(report_date=None)
    assert ingest_documents.document_title(filing) == "AAPL 10-K 2024-11-01"


def test_filing_date_parses_iso_date_to_utc_datetime():
    assert ingest_documents.filing_date("2024-11-01") == datetime(2024, 11, 1, tzinfo=UTC)


def test_filing_date_none_returns_none():
    assert ingest_documents.filing_date(None) is None


def test_ingest_filing_inserts_new_document(tmp_path, session):
    filing = make_filing()
    write_markdown(tmp_path, filing, "# Apple 10-K\n\nRevenue grew.")

    existing_by_url: dict[str, SourceDocument] = {}
    result = ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=False, org_id=ORG_ID)

    assert result == "inserted"
    assert filing["source_url"] in existing_by_url
    assert existing_by_url[filing["source_url"]].company_ticker == "AAPL"


def test_ingest_filing_skips_existing_when_not_updating(tmp_path, session):
    filing = make_filing()
    write_markdown(tmp_path, filing, "content")

    existing = SourceDocument(
        id=uuid4(),
        title="stale title",
        source_url=filing["source_url"],
        content_markdown="old content",
    )
    existing_by_url = {filing["source_url"]: existing}

    result = ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=False, org_id=ORG_ID)

    assert result == "skipped"
    assert existing.title == "stale title"


def test_ingest_filing_updates_existing_when_updating(tmp_path, session):
    filing = make_filing()
    write_markdown(tmp_path, filing, "fresh content")

    existing = SourceDocument(
        id=uuid4(),
        title="stale title",
        source_url=filing["source_url"],
        content_markdown="old content",
    )
    existing_by_url = {filing["source_url"]: existing}

    result = ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=True, org_id=ORG_ID)

    assert result == "updated"
    assert existing.content_markdown == "fresh content"
    assert existing.title == "AAPL 10-K 2024-09-28"


def test_ingest_filing_raises_when_markdown_missing(tmp_path, session):
    filing = make_filing()
    with pytest.raises(FileNotFoundError):
        ingest_documents.ingest_filing(session, filing, tmp_path, {}, update=False, org_id=ORG_ID)


def test_ingest_filing_assigns_the_organization(tmp_path, session):
    filing = make_filing()
    write_markdown(tmp_path, filing, "content")

    existing_by_url: dict[str, SourceDocument] = {}
    ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=False, org_id=ORG_ID)

    assert existing_by_url[filing["source_url"]].org_id == ORG_ID


def test_ingest_filing_update_assigns_organization_to_existing_document(tmp_path, session):
    filing = make_filing()
    write_markdown(tmp_path, filing, "content")
    existing = SourceDocument(
        id=uuid4(), title="old", source_url=filing["source_url"], content_markdown="old", org_id=None
    )

    ingest_documents.ingest_filing(
        session, filing, tmp_path, {filing["source_url"]: existing}, update=True, org_id=ORG_ID
    )

    assert existing.org_id == ORG_ID


def test_select_filings_filters_by_ticker_case_insensitively():
    filings = [make_filing(ticker="AMZN"), make_filing(ticker="AAPL"), make_filing(ticker="amzn")]

    assert ingest_documents.select_filings(filings, "amzn") == [filings[0], filings[2]]
    assert ingest_documents.select_filings(filings, None) == filings


def write_manifest(path: Path, filings: list[dict]) -> Path:
    import json

    manifest = path / "manifest.json"
    manifest.write_text(json.dumps({"filings": filings}), encoding="utf-8")
    return manifest


def test_ingest_directory_rejects_unknown_organization_and_writes_nothing(
    tmp_path, session_factory, monkeypatch
):
    filing = make_filing()
    write_markdown(tmp_path, filing, "content")
    manifest = write_manifest(tmp_path, [filing])
    monkeypatch.setattr(ingest_documents, "SessionLocal", session_factory)

    with pytest.raises(ValueError, match="does not exist"):
        ingest_documents.ingest_directory(tmp_path, manifest, update=False, org_slug="nosuchorg")

    with session_factory() as db:
        assert db.query(SourceDocument).count() == 0


def test_ingest_directory_assigns_org_and_only_imports_the_selected_ticker(
    tmp_path, session_factory, monkeypatch
):
    amzn = make_filing(ticker="AMZN", source_url="https://sec/amzn", local_path="2024/amzn.htm")
    aapl = make_filing(ticker="AAPL", source_url="https://sec/aapl", local_path="2024/aapl.htm")
    write_markdown(tmp_path, amzn, "amazon content")
    write_markdown(tmp_path, aapl, "apple content")
    manifest = write_manifest(tmp_path, [amzn, aapl])
    monkeypatch.setattr(ingest_documents, "SessionLocal", session_factory)

    with session_factory.begin() as db:
        org = Organization(slug="amazon", name="Amazon")
        db.add(org)
        db.flush()
        org_id = org.id

    counts = ingest_documents.ingest_directory(
        tmp_path, manifest, update=False, org_slug="Amazon", ticker="AMZN"
    )

    assert counts == {"inserted": 1, "updated": 0, "skipped": 0}
    with session_factory() as db:
        documents = db.query(SourceDocument).all()
        assert [(d.company_ticker, d.org_id) for d in documents] == [("AMZN", org_id)]


def test_ingest_directory_rejects_ticker_with_no_filings(tmp_path, session_factory, monkeypatch):
    manifest = write_manifest(tmp_path, [make_filing(ticker="AAPL")])
    monkeypatch.setattr(ingest_documents, "SessionLocal", session_factory)

    with pytest.raises(ValueError, match="No filings"):
        ingest_documents.ingest_directory(tmp_path, manifest, update=False, org_slug="amazon", ticker="META")
