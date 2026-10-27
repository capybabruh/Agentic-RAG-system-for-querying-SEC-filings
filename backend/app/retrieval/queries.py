"""Bounded pgvector and Postgres full-text queries over document_chunks.

Raw SQL (not the ORM) is used deliberately: pgvector's distance operators and
`ts_rank` aren't natural ORM expressions, and keeping these as two small,
parameterized, single-purpose queries keeps agent-facing retrieval bounded
(see docs/architecture.md's "Retrieval Strategy" — no agent-generated SQL).

Both queries are scoped to `allowed_org_ids`: only chunks whose source document
belongs to one of the caller's organizations can ever be returned. Documents
with no organization (org_id IS NULL) never match.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class RankedChunkId:
    chunk_id: uuid.UUID
    rank: int  # 0-based position within this single ranking
    score: float  # raw similarity/rank score, for observability only — not used for fusion


def _pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(value) for value in embedding) + "]"


def vector_search(
    db: Session,
    query_embedding: list[float],
    limit: int,
    ticker: str | None = None,
    filing_type: str | None = None,
    *,
    allowed_org_ids: Sequence[uuid.UUID],
) -> list[RankedChunkId]:
    """Semantic search ordered by cosine distance (matches the HNSW vector_cosine_ops index)."""
    if not allowed_org_ids:
        return []
    sql = """
        SELECT c.id AS chunk_id, (c.embedding <=> CAST(:query_embedding AS vector)) AS distance
        FROM document_chunks c
        JOIN source_documents d ON d.id = c.source_document_id
        WHERE d.org_id = ANY(CAST(:allowed_org_ids AS uuid[]))
          AND (CAST(:ticker AS varchar) IS NULL OR d.company_ticker = CAST(:ticker AS varchar))
          AND (CAST(:filing_type AS varchar) IS NULL OR d.filing_type = CAST(:filing_type AS varchar))
        ORDER BY distance ASC
        LIMIT :limit
    """
    rows = db.execute(
        text(sql),
        {
            "query_embedding": _pgvector_literal(query_embedding),
            "allowed_org_ids": list(allowed_org_ids),
            "ticker": ticker,
            "filing_type": filing_type,
            "limit": limit,
        },
    ).all()
    return [
        RankedChunkId(chunk_id=row.chunk_id, rank=rank, score=float(row.distance))
        for rank, row in enumerate(rows)
    ]


def fulltext_search(
    db: Session,
    query: str,
    limit: int,
    ticker: str | None = None,
    filing_type: str | None = None,
    *,
    allowed_org_ids: Sequence[uuid.UUID],
) -> list[RankedChunkId]:
    """Lexical search ranked by ts_rank over the generated search_vector column."""
    if not allowed_org_ids:
        return []
    sql = """
        SELECT c.id AS chunk_id,
               ts_rank(c.search_vector, websearch_to_tsquery('english', :query)) AS rank_score
        FROM document_chunks c
        JOIN source_documents d ON d.id = c.source_document_id
        WHERE c.search_vector @@ websearch_to_tsquery('english', :query)
          AND d.org_id = ANY(CAST(:allowed_org_ids AS uuid[]))
          AND (CAST(:ticker AS varchar) IS NULL OR d.company_ticker = CAST(:ticker AS varchar))
          AND (CAST(:filing_type AS varchar) IS NULL OR d.filing_type = CAST(:filing_type AS varchar))
        ORDER BY rank_score DESC
        LIMIT :limit
    """
    rows = db.execute(
        text(sql),
        {
            "query": query,
            "allowed_org_ids": list(allowed_org_ids),
            "ticker": ticker,
            "filing_type": filing_type,
            "limit": limit,
        },
    ).all()
    return [
        RankedChunkId(chunk_id=row.chunk_id, rank=rank, score=float(row.rank_score))
        for rank, row in enumerate(rows)
    ]
