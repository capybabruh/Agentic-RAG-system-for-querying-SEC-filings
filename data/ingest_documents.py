"""Import converted filing Markdown into the source_documents table.

Run from the backend directory with:
    uv run python ../data/ingest_documents.py --org amazon --ticker AMZN

Every imported document is assigned to the organization named by --org, which
must already exist (see backend/scripts/manage_orgs.py). Only members of that
organization can retrieve it. To assign already-imported documents, re-run with
--update; chunks inherit the organization from their document, so no
re-embedding is needed.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.database.models import SourceDocument
from app.database.organizations import get_org_by_slug
from app.database.session import SessionLocal
from sqlalchemy import select
from sqlalchemy.orm import Session

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_MARKDOWN_DIR = DATA_DIR / "markdown"
DEFAULT_MANIFEST_PATH = DATA_DIR / "downloads" / "manifest.json"


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def filing_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)


def document_title(filing: dict[str, Any]) -> str:
    return f"{filing['ticker']} {filing['form']} {filing.get('report_date') or filing['filing_date']}"


def ingest_filing(
    db: Session,
    filing: dict[str, Any],
    markdown_dir: Path,
    existing_by_url: dict[str, SourceDocument],
    update: bool,
    org_id: uuid.UUID,
) -> str:
    local_path = markdown_dir / Path(filing["local_path"]).with_suffix(".md")
    if not local_path.exists():
        raise FileNotFoundError(f"Markdown file does not exist: {local_path}")

    source_url = filing["source_url"]
    existing = existing_by_url.get(source_url)
    if existing is not None and not update:
        return "skipped"

    metadata = {
        "cik": filing.get("cik"),
        "report_date": filing.get("report_date"),
        "accession_number": filing.get("accession_number"),
        "primary_document": filing.get("primary_document"),
        "local_path": filing.get("local_path"),
        "source": "SEC EDGAR",
    }
    values = {
        "org_id": org_id,
        "title": document_title(filing),
        "company_ticker": filing.get("ticker"),
        "filing_type": filing.get("form"),
        "filing_date": filing_date(filing.get("filing_date")),
        "source_url": source_url,
        "content_markdown": local_path.read_text(encoding="utf-8"),
        "document_metadata": metadata,
    }

    if existing is None:
        document = SourceDocument(**values)
        db.add(document)
        existing_by_url[source_url] = document
        return "inserted"

    for field, value in values.items():
        setattr(existing, field, value)
    return "updated"


def select_filings(filings: list[dict[str, Any]], ticker: str | None) -> list[dict[str, Any]]:
    if ticker is None:
        return filings
    wanted = ticker.strip().upper()
    return [filing for filing in filings if str(filing.get("ticker", "")).upper() == wanted]


def ingest_directory(
    markdown_dir: Path,
    manifest_path: Path,
    update: bool,
    org_slug: str,
    ticker: str | None = None,
) -> dict[str, int]:
    manifest = load_manifest(manifest_path)
    filings = manifest.get("filings", [])
    if not isinstance(filings, list):
        raise TypeError("Manifest filings must be a list")
    filings = select_filings(filings, ticker)
    if not filings:
        raise ValueError(f"No filings in the manifest match ticker {ticker!r}")

    with SessionLocal.begin() as db:
        org = get_org_by_slug(db, org_slug.strip().lower())
        if org is None:
            raise ValueError(
                f"Organization '{org_slug}' does not exist — create it with "
                "backend/scripts/manage_orgs.py create-org first"
            )
        existing_documents = db.scalars(select(SourceDocument)).all()
        existing_by_url = {
            document.source_url: document
            for document in existing_documents
            if document.source_url
        }
        counts = {"inserted": 0, "updated": 0, "skipped": 0}
        for filing in filings:
            result = ingest_filing(db, filing, markdown_dir, existing_by_url, update, org.id)
            counts[result] += 1
            print(f"{result.capitalize()}: {filing['local_path']}")

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--markdown-dir",
        type=Path,
        default=DEFAULT_MARKDOWN_DIR,
        help=f"Markdown directory (default: {DEFAULT_MARKDOWN_DIR})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help=f"Download manifest path (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--org",
        required=True,
        help="Slug of the organization that owns these documents, e.g. amazon.",
    )
    parser.add_argument(
        "--ticker",
        help="Only import manifest filings for this ticker, e.g. AMZN.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update already-imported documents from their Markdown files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        counts = ingest_directory(
            args.markdown_dir.resolve(),
            args.manifest.resolve(),
            args.update,
            args.org,
            args.ticker,
        )
    except ValueError as error:
        raise SystemExit(f"Error: {error}") from error
    print(
        "Imported documents: "
        f"{counts['inserted']} inserted, {counts['updated']} updated, "
        f"{counts['skipped']} skipped"
    )


if __name__ == "__main__":
    main()
