from __future__ import annotations

from uuid import uuid4

from app.config import settings
from app.retrieval.fusion import reciprocal_rank_fusion


def test_top_result_from_both_rankings_wins():
    a, b, c = uuid4(), uuid4(), uuid4()
    fused = reciprocal_rank_fusion([[a, b, c], [b, a, c]])

    assert [chunk_id for chunk_id, _ in fused] == [a, b, c]


def test_scores_sum_across_rankings():
    a, b = uuid4(), uuid4()
    fused = dict(reciprocal_rank_fusion([[a, b], [b, a]], k=60))

    expected = 1.0 / 61 + 1.0 / 62
    assert fused[a] == expected
    assert fused[b] == expected


def test_id_present_in_only_one_ranking_still_scores():
    a, b = uuid4(), uuid4()
    fused = dict(reciprocal_rank_fusion([[a], []]))

    assert fused[a] == 1.0 / (settings.retrieval_rrf_k + 1)
    assert b not in fused


def test_empty_rankings_produce_empty_result():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_custom_k_changes_score_magnitude_not_order():
    a, b = uuid4(), uuid4()
    fused_default = dict(reciprocal_rank_fusion([[a, b]]))
    fused_custom = dict(reciprocal_rank_fusion([[a, b]], k=1))

    assert fused_default[a] > fused_default[b]
    assert fused_custom[a] > fused_custom[b]
    assert fused_custom[a] > fused_default[a]
