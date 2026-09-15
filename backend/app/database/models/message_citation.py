from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UUID, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.chat_message import ChatMessage
    from app.database.models.document_chunk import DocumentChunk


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    message: Mapped["ChatMessage"] = relationship(back_populates="citations")
    chunk: Mapped["DocumentChunk | None"] = relationship(back_populates="citations")

    # Proxied source-document metadata for citation display — None if the
    # source chunk has since been deleted (chunk_id is nullable, ON DELETE
    # SET NULL). Callers should eager-load chunk.source_document to avoid
    # N+1 queries (see database/chats.py's selectinload chains).
    @property
    def ticker(self) -> str | None:
        return self.chunk.source_document.company_ticker if self.chunk else None

    @property
    def filing_type(self) -> str | None:
        return self.chunk.source_document.filing_type if self.chunk else None

    @property
    def filing_date(self) -> datetime | None:
        return self.chunk.source_document.filing_date if self.chunk else None

    @property
    def document_title(self) -> str | None:
        return self.chunk.source_document.title if self.chunk else None

    @property
    def source_url(self) -> str | None:
        return self.chunk.source_document.source_url if self.chunk else None
