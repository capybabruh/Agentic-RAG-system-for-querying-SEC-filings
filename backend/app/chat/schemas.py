from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class CitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_id: uuid.UUID | None
    quote_text: str
    page_number: int | None
    section_label: str | None
    ticker: str | None = None
    filing_type: str | None = None
    filing_date: datetime | None = None
    document_title: str | None = None
    source_url: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    sender: str
    content: str
    message_metadata: dict[str, object] | None
    created_at: datetime
    citations: list[CitationResponse] = []


class MessagePart(BaseModel):
    type: str
    text: str | None = None


class AiSdkMessage(BaseModel):
    id: str | None = None
    role: Literal["system", "user", "assistant"]
    content: str | None = None
    parts: list[MessagePart] = Field(default_factory=list)

    def text(self) -> str:
        if self.content:
            return self.content
        return "".join(part.text or "" for part in self.parts if part.type == "text")


class ChatStreamRequest(BaseModel):
    thread_id: uuid.UUID = Field(alias="threadId")
    messages: list[AiSdkMessage]

    model_config = ConfigDict(populate_by_name=True)
