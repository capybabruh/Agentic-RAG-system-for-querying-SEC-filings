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
from app.database.models import SourceDocument


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[SourceDocument.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


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
    result = ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=False)

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

    result = ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=False)

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

    result = ingest_documents.ingest_filing(session, filing, tmp_path, existing_by_url, update=True)

    assert result == "updated"
    assert existing.content_markdown == "fresh content"
    assert existing.title == "AAPL 10-K 2024-09-28"


def test_ingest_filing_raises_when_markdown_missing(tmp_path, session):
    filing = make_filing()
    with pytest.raises(FileNotFoundError):
        ingest_documents.ingest_filing(session, filing, tmp_path, {}, update=False)
