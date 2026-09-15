"""Chunk filings with Docling and store Mistral embeddings in Supabase Postgres.

Run from the backend directory with:
    uv run python ../data/ingest_chunks.py --smoke-test
    uv run python ../data/ingest_chunks.py
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tiktoken
from docling.chunking import HierarchicalChunker, HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from mistralai.client import Mistral
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from app.database.session import SessionLocal

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = DATA_DIR / "downloads"
DEFAULT_MANIFEST_PATH = DATA_DIR / "downloads" / "manifest.json"
DEFAULT_MAX_TOKENS = 800
DEFAULT_BATCH_SIZE = 64


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tokenizer_for_model(max_tokens: int) -> OpenAITokenizer:
    # tiktoken provides a stable token-count estimate for chunk sizing; Mistral's
    # embedding API validates the final request independently.
    encoding = tiktoken.get_encoding("cl100k_base")
    return OpenAITokenizer(tokenizer=encoding, max_tokens=max_tokens)


def make_chunker(kind: str, max_tokens: int):
    # HybridChunker splits on document structure and merges undersized peers rather
    # than sliding a fixed-size window, so there's no literal token "overlap" to set here.
    # Cross-chunk context for grounding comes from retrieval/retriever.py's
    # read_surrounding_chunks(), which walks chunk_index neighbors instead.
    if kind == "hierarchical":
        return HierarchicalChunker(always_emit_headings=True)
    return HybridChunker(
        tokenizer=tokenizer_for_model(max_tokens),
        always_emit_headings=True,
        repeat_table_header=True,
        merge_peers=True,
    )


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return jsonable(vars(value))
    return str(value)


def chunk_page_number(raw_meta: dict[str, Any]) -> int | None:
    # docling's page_no lives per-provenance-item under doc_items, not top-level on meta:
    # meta.doc_items[i].prov[j].page_no. A chunk can span multiple doc_items/pages, so we
    # report the earliest page it touches.
    doc_items = raw_meta.get("doc_items")
    if not isinstance(doc_items, list):
        return None
    page_numbers = [
        prov["page_no"]
        for item in doc_items
        if isinstance(item, dict)
        for prov in item.get("prov", [])
        if isinstance(prov, dict) and isinstance(prov.get("page_no"), int)
    ]
    return min(page_numbers) if page_numbers else None


def chunk_section_label(raw_meta: dict[str, Any]) -> str | None:
    headings = raw_meta.get("headings")
    if isinstance(headings, list) and headings:
        return str(headings[-1])
    return None


def chunk_metadata(chunk: Any, filing: dict[str, Any], chunker_name: str, model: str) -> dict[str, Any]:
    raw_meta = jsonable(getattr(chunk, "meta", None))
    metadata = {
        "ticker": filing.get("ticker"),
        "filing_type": filing.get("form"),
        "filing_year": (filing.get("report_date") or filing.get("filing_date", ""))[:4],
        "filing_date": filing.get("filing_date"),
        "report_date": filing.get("report_date"),
        "accession_number": filing.get("accession_number"),
        "source_url": filing.get("source_url"),
        "chunker": chunker_name,
        "embedding_model": model,
        "docling_metadata": raw_meta,
    }
    if isinstance(raw_meta, dict):
        page_number = chunk_page_number(raw_meta)
        section_label = chunk_section_label(raw_meta)
        if page_number is not None:
            metadata["page_number"] = page_number
        if section_label is not None:
            metadata["section_label"] = section_label
    return metadata


def chunk_text(chunker: Any, chunk: Any) -> tuple[str, str, int]:
    plain_text = str(getattr(chunk, "text", "")).strip()
    if not plain_text:
        raise ValueError("Docling returned an empty chunk")
    embedding_text = chunker.contextualize(chunk) if hasattr(chunker, "contextualize") else plain_text
    tokenizer = getattr(chunker, "tokenizer", None)
    token_count = tokenizer.count_tokens(embedding_text) if tokenizer else 0
    return plain_text, embedding_text, token_count


def embedding_batches(client: Mistral, texts: list[str], batch_size: int) -> Iterable[list[list[float]]]:
    for start in range(0, len(texts), batch_size):
        response = client.embeddings.create(
            model=settings.mistral_embedding_model,
            inputs=texts[start : start + batch_size],
        )
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        for vector in vectors:
            if len(vector) != settings.mistral_embedding_dimensions:
                raise ValueError(
                    "Embedding dimension mismatch: "
                    f"expected {settings.mistral_embedding_dimensions}, got {len(vector)}"
                )
        yield vectors


def source_document_for(db: Session, source_url: str) -> SourceDocument:
    document = db.scalar(select(SourceDocument).where(SourceDocument.source_url == source_url))
    if document is None:
        raise LookupError(f"No source_documents row exists for {source_url}")
    return document


def ingest_document(
    db: Session,
    client: Mistral,
    filing: dict[str, Any],
    input_dir: Path,
    kind: str,
    max_tokens: int,
    batch_size: int,
    update: bool,
    limit: int | None = None,
) -> int:
    html_path = input_dir / Path(filing["local_path"])
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file does not exist: {html_path}")

    document = source_document_for(db, filing["source_url"])
    if not update and db.scalar(
        select(DocumentChunk.id).where(DocumentChunk.source_document_id == document.id).limit(1)
    ):
        return 0

    if update:
        db.execute(delete(DocumentChunk).where(DocumentChunk.source_document_id == document.id))

    converted = DocumentConverter().convert(html_path)
    chunker = make_chunker(kind, max_tokens)
    chunks = list(chunker.chunk(converted.document))
    if limit is not None:
        chunks = chunks[:limit]
    prepared = [chunk_text(chunker, chunk) for chunk in chunks]
    embeddings = [vector for batch in embedding_batches(client, [item[1] for item in prepared], batch_size) for vector in batch]

    for index, (chunk, prepared_chunk, embedding) in enumerate(zip(chunks, prepared, embeddings, strict=True)):
        plain_text, _, token_count = prepared_chunk
        metadata = chunk_metadata(chunk, filing, kind, settings.mistral_embedding_model)
        db.add(
            DocumentChunk(
                source_document_id=document.id,
                chunk_index=index,
                page_number=metadata.get("page_number"),
                section_label=metadata.get("section_label"),
                chunk_text=plain_text,
                token_count=token_count,
                embedding=embedding,
                chunk_metadata=metadata,
            )
        )
    return len(chunks)


def select_filings(manifest: dict[str, Any], smoke_test: bool) -> list[dict[str, Any]]:
    filings = manifest.get("filings", [])
    if not isinstance(filings, list) or not filings:
        raise ValueError("Manifest must contain a non-empty filings list")
    return filings[:1] if smoke_test else filings


def verify_smoke_chunk(source_url: str) -> None:
    with SessionLocal() as db:
        row = db.execute(
            select(DocumentChunk, SourceDocument)
            .join(SourceDocument, DocumentChunk.source_document_id == SourceDocument.id)
            .where(SourceDocument.source_url == source_url)
            .order_by(DocumentChunk.chunk_index)
            .limit(1)
        ).first()
        if row is None:
            raise RuntimeError("Smoke test inserted no document chunk")
        chunk, document = row
        if not chunk.embedding or not chunk.chunk_text.strip():
            raise RuntimeError("Smoke test chunk has no text or embedding")
        search_vector_present = db.scalar(
            select(DocumentChunk.id)
            .where(DocumentChunk.id == chunk.id, DocumentChunk.search_vector.is_not(None))
        )
        if search_vector_present is None:
            raise RuntimeError("Smoke test chunk has no generated search_vector")
        print(
            "Smoke test verified: "
            f"document={document.title}, chunk_id={chunk.id}, "
            f"dimensions={len(chunk.embedding)}, tokens={chunk.token_count}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--chunker", choices=("hybrid", "hierarchical"), default="hybrid")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--smoke-test", action="store_true", help="Embed and insert one chunk only.")
    parser.add_argument("--update", action="store_true", help="Replace existing chunks for each document.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_tokens <= 0 or args.batch_size <= 0:
        raise ValueError("--max-tokens and --batch-size must be positive")

    manifest = load_manifest(args.manifest.resolve())
    filings = select_filings(manifest, args.smoke_test)
    client = Mistral(api_key=settings.mistral_api_key)
    total = 0
    for filing in filings:
        with SessionLocal.begin() as db:
            count = ingest_document(
                db,
                client,
                filing,
                args.input_dir.resolve(),
                args.chunker,
                args.max_tokens,
                args.batch_size,
                args.update,
                limit=1 if args.smoke_test else None,
            )
        total += count
        print(f"{filing['ticker']} {filing['report_date']}: {count} chunk(s)")
    if args.smoke_test:
        verify_smoke_chunk(filings[0]["source_url"])
    print(f"Inserted chunks: {total}")


if __name__ == "__main__":
    main()
