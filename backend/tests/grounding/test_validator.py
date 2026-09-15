from __future__ import annotations

import uuid

import pytest

from app.assistant.outputs import Citation, GroundedAnswer
from app.grounding.validator import GroundingError, validate_citations


def test_valid_answer_with_matching_citation_passes():
    chunk_id = uuid.uuid4()
    answer = GroundedAnswer(
        answer="Revenue grew.",
        citations=[Citation(chunk_id=chunk_id, quote_text="Revenue grew year over year.")],
        has_sufficient_evidence=True,
    )

    validate_citations(answer, {chunk_id})


def test_no_evidence_answer_with_no_citations_passes():
    answer = GroundedAnswer(answer="The corpus does not cover this.", citations=[], has_sufficient_evidence=False)

    validate_citations(answer, set())


def test_citation_referencing_unretrieved_chunk_is_rejected():
    retrieved = uuid.uuid4()
    cited = uuid.uuid4()
    answer = GroundedAnswer(
        answer="Revenue grew.",
        citations=[Citation(chunk_id=cited, quote_text="...")],
        has_sufficient_evidence=True,
    )

    with pytest.raises(GroundingError):
        validate_citations(answer, {retrieved})


def test_sufficient_evidence_without_citations_is_rejected():
    answer = GroundedAnswer(answer="Revenue grew.", citations=[], has_sufficient_evidence=True)

    with pytest.raises(GroundingError):
        validate_citations(answer, set())


def test_hedged_answer_with_partial_citations_passes():
    # A real, desirable shape: the corpus only partially answers the question, the
    # model says so (has_sufficient_evidence=False) but still cites the real partial
    # evidence it found rather than citing nothing — this is more trustworthy than a
    # confident but unsupported answer, so it must NOT be rejected.
    chunk_id = uuid.uuid4()
    answer = GroundedAnswer(
        answer="The filings don't cover all five years, but here's what's available.",
        citations=[Citation(chunk_id=chunk_id, quote_text="...")],
        has_sufficient_evidence=False,
    )

    validate_citations(answer, {chunk_id})
