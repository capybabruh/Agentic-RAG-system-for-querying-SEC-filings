"""Enforces the product's trust contract: answers must cite retrieved evidence.

See docs/architecture.md's "Grounding and Citation Policy" — this is architecture,
not a prompt preference, so it's checked in code after every agent run.
"""
from __future__ import annotations

import uuid

from app.assistant.outputs import GroundedAnswer


class GroundingError(Exception):
    """Raised when an agent's answer violates the citation/evidence contract."""


def validate_citations(answer: GroundedAnswer, retrieved_chunk_ids: set[uuid.UUID]) -> None:
    for citation in answer.citations:
        if citation.chunk_id not in retrieved_chunk_ids:
            raise GroundingError(
                f"Citation references chunk {citation.chunk_id}, which was not retrieved this run"
            )

    if answer.has_sufficient_evidence and not answer.citations:
        raise GroundingError("Answer claims sufficient evidence but has no citations")

    # A partial/hedged answer ("data is incomplete, but here's what I found") is a
    # legitimate, trustworthy shape: has_sufficient_evidence=False alongside real
    # citations to the partial evidence it did retrieve. Only a real trust violation
    # — a citation to something never retrieved — is blocked above; the evidence flag
    # is not required to move in lockstep with citation presence.
