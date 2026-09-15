from __future__ import annotations

import uuid

from pydantic import BaseModel


class Citation(BaseModel):
    chunk_id: uuid.UUID
    quote_text: str
    page_number: int | None = None
    section_label: str | None = None


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[Citation] = []
    has_sufficient_evidence: bool
