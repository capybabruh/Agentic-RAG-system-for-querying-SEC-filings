from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UUID,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.message_citation import MessageCitation
    from app.database.models.source_document import SourceDocument


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(chunk_text, ''))", persisted=True),
        nullable=False,
    )
    chunk_metadata: Mapped[dict[str, Any] | None] = mapped_column(
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

    source_document: Mapped["SourceDocument"] = relationship(back_populates="chunks")
    citations: Mapped[list["MessageCitation"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_document_chunks_document_order", "source_document_id", "chunk_index"),
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )
