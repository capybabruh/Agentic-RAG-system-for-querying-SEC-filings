from __future__ import annotations

import uuid
from datetime import UTC, datetime

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import ChatMessage, ChatThread, MessageCitation
from app.database.models.document_chunk import DocumentChunk

_CITATION_LOAD_OPTIONS = selectinload(ChatMessage.citations).selectinload(
    MessageCitation.chunk
).selectinload(DocumentChunk.source_document)


@dataclass
class CitationInput:
    chunk_id: uuid.UUID
    quote_text: str
    page_number: int | None = None
    section_label: str | None = None


def list_threads(db: Session, user_id: uuid.UUID) -> list[ChatThread]:
    return list(
        db.scalars(
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc())
        )
    )


def create_thread(db: Session, user_id: uuid.UUID, title: str | None) -> ChatThread:
    thread = ChatThread(user_id=user_id, title=title)
    db.add(thread)
    db.flush()
    return thread


def get_thread(db: Session, thread_id: uuid.UUID) -> ChatThread | None:
    return db.scalar(select(ChatThread).where(ChatThread.id == thread_id))


def delete_thread(db: Session, thread: ChatThread) -> None:
    db.delete(thread)


def list_messages(db: Session, thread_id: uuid.UUID) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .options(_CITATION_LOAD_OPTIONS)
        )
    )


def get_message_citations(db: Session, message_id: uuid.UUID) -> list[MessageCitation]:
    return list(
        db.scalars(
            select(MessageCitation)
            .where(MessageCitation.message_id == message_id)
            .options(
                selectinload(MessageCitation.chunk).selectinload(DocumentChunk.source_document)
            )
        )
    )


def create_message(
    db: Session,
    thread_id: uuid.UUID,
    sender: str,
    content: str,
    metadata: dict[str, object] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        thread_id=thread_id,
        sender=sender,
        content=content,
        message_metadata=metadata,
        created_at=datetime.now(UTC),
    )
    db.add(message)
    db.flush()
    return message


def create_citations(
    db: Session, message_id: uuid.UUID, citations: list[CitationInput]
) -> list[MessageCitation]:
    rows = [
        MessageCitation(
            message_id=message_id,
            chunk_id=citation.chunk_id,
            quote_text=citation.quote_text,
            page_number=citation.page_number,
            section_label=citation.section_label,
        )
        for citation in citations
    ]
    db.add_all(rows)
    db.flush()
    return rows
