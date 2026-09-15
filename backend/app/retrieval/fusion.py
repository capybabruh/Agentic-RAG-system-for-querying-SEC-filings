"""Reciprocal Rank Fusion for combining independently-ranked chunk-id lists.

RRF combines ranks rather than raw scores because vector cosine distance and
Postgres ts_rank live on incomparable scales — see docs/architecture.md's
"Retrieval Strategy". The default k (see app.config.settings.retrieval_rrf_k,
60) follows the original RRF paper's smoothing constant, also used unchanged
in the ai-cookbook hybrid-retrieval reference implementation.
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from app.config import settings


def reciprocal_rank_fusion(
    rankings: list[list[uuid.UUID]], k: int = settings.retrieval_rrf_k
) -> list[tuple[uuid.UUID, float]]:
    """Fuse multiple ranked id lists into one list of (chunk_id, fused_score), best first."""
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
