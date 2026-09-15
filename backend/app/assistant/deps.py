from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.retrieval.retriever import DocumentRetriever


@dataclass
class DocumentAgentDeps:
    user_id: str
    thread_id: str
    db: Session
    retriever: DocumentRetriever
    # Populated by the search_filings/read_chunk/read_surrounding_chunks tools as they run,
    # so grounding validation can confirm every citation traces back to something retrieved
    # this turn (see app/grounding/validator.py).
    retrieved_chunk_ids: set[uuid.UUID] = field(default_factory=set)
    # PydanticAI runs sync tool functions in worker threads and may call several tools
    # concurrently; SQLAlchemy's Session is not thread-safe, so every tool call must
    # serialize its use of `db` through this lock instead of hitting it in parallel.
    db_lock: threading.Lock = field(default_factory=threading.Lock)
    # Optional progress callback: tools/orchestrator call on_status(stage, message) with
    # human-readable updates so a streaming caller can show what's happening while it
    # waits (see chat/orchestrator.py::run_chat_turn, api/chat.py's /chat/stream). Called
    # synchronously and possibly from a worker thread — callers that need to cross back
    # into an event loop must do their own thread-safe handoff (e.g. loop.call_soon_threadsafe).
    on_status: Callable[[str, str], None] | None = None
