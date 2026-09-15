"""Smoke test for the retrieval layer only: embed + hybrid search, no LLM generation.

Requires a live Mistral key (embeddings only — cheap compared to smoke_assistant.py,
which also drives full chat completions). Calls DocumentRetriever.search() against
the real ingested corpus. Read-only — writes nothing to Supabase.

Run from backend/ with:
    uv run python scripts/smoke_retrieval.py
"""
from __future__ import annotations

from mistralai.client import Mistral

from app.config import settings
from app.database.session import SessionLocal
from app.retrieval.retriever import DocumentRetriever

QUERIES = [
    (
        "Across Apple's 2021-2025 10-Ks, how did the revenue mix between iPhone, Services, "
        "Mac, iPad, and Wearables change?",
        "AAPL",
    ),
    (
        "How did NVIDIA describe demand drivers and supply constraints for its Data Center business?",
        "NVDA",
    ),
]


def run_one(retriever: DocumentRetriever, db, query: str, ticker: str) -> None:
    print("=" * 100)
    print("Q:", query)
    passages = retriever.search(db, query, top_k=3, ticker=ticker)
    if not passages:
        print("  (no passages returned)")
        return
    for passage in passages:
        print("-" * 80)
        print(
            f"ticker={passage.ticker} filing_type={passage.filing_type} year={passage.filing_year} "
            f"section={passage.section_label} page={passage.page_number} score={passage.score:.5f}"
        )
        print(passage.chunk_text[:300].replace("\n", " "))


def main() -> None:
    client = Mistral(api_key=settings.mistral_api_key)
    retriever = DocumentRetriever(client, settings.mistral_embedding_model)

    with SessionLocal() as db:
        for query, ticker in QUERIES:
            run_one(retriever, db, query, ticker)


if __name__ == "__main__":
    main()
