"""Integration tests against the real ingested Supabase/pgvector corpus.

Needs live DATABASE_URL + MISTRAL_API_KEY credentials and an already-ingested
corpus (see data/ingest_documents.py, data/ingest_chunks.py). Run with:
    uv run pytest -m integration tests/retrieval/test_queries.py
"""
from __future__ import annotations

import pytest
from mistralai.client import Mistral
from sqlalchemy import text

from app.config import settings
from app.database.session import SessionLocal
from app.retrieval.queries import fulltext_search, vector_search

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="module")
def mistral_client():
    return Mistral(api_key=settings.mistral_api_key)


def embed(client: Mistral, text_: str) -> list[float]:
    response = client.embeddings.create(model=settings.mistral_embedding_model, inputs=[text_])
    return response.data[0].embedding


def tickers_for(db, chunk_ids) -> set[str | None]:
    if not chunk_ids:
        return set()
    rows = db.execute(
        text(
            """
            SELECT DISTINCT d.company_ticker
            FROM document_chunks c
            JOIN source_documents d ON d.id = c.source_document_id
            WHERE c.id = ANY(:chunk_ids)
            """
        ),
        {"chunk_ids": list(chunk_ids)},
    ).all()
    return {row[0] for row in rows}


def test_vector_search_returns_results_ordered_by_ascending_distance(db, mistral_client):
    embedding = embed(mistral_client, "iPhone revenue and Services segment growth")

    results = vector_search(db, embedding, limit=10)

    assert results
    scores = [r.score for r in results]
    assert scores == sorted(scores)


def test_vector_search_respects_limit(db, mistral_client):
    embedding = embed(mistral_client, "cloud infrastructure capital expenditures")

    results = vector_search(db, embedding, limit=3)

    assert len(results) <= 3


def test_vector_search_filters_by_ticker(db, mistral_client):
    embedding = embed(mistral_client, "iPhone revenue and Services segment growth")

    results = vector_search(db, embedding, limit=10, ticker="AAPL")

    assert results
    assert tickers_for(db, [r.chunk_id for r in results]) == {"AAPL"}


def test_fulltext_search_returns_results_for_known_term(db):
    results = fulltext_search(db, "iPhone", limit=10, ticker="AAPL")

    assert results
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_fulltext_search_filters_by_filing_type(db):
    results = fulltext_search(db, "revenue", limit=10, ticker="NVDA", filing_type="10-K")

    assert results
    assert tickers_for(db, [r.chunk_id for r in results]) == {"NVDA"}


def test_fulltext_search_no_match_returns_empty(db):
    results = fulltext_search(db, "xyzzyplughnonsenseterm", limit=10)

    assert results == []
