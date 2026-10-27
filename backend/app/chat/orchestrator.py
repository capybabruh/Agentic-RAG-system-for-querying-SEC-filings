"""Coordinates one chat turn end-to-end: retrieve, generate, validate, persist."""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import lru_cache

from mistralai.client import Mistral
from sqlalchemy.orm import Session

from app.assistant.agent import document_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.config import settings
from app.database import chats
from app.database.chats import CitationInput
from app.database.models import ChatMessage
from app.database.organizations import get_user_org_ids
from app.grounding.validator import validate_citations
from app.retrieval.retriever import DocumentRetriever

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _default_retriever() -> DocumentRetriever:
    client = Mistral(api_key=settings.mistral_api_key)
    return DocumentRetriever(client, settings.mistral_embedding_model)


async def run_chat_turn(
    db: Session,
    thread_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message: str,
    retriever: DocumentRetriever | None = None,
    status_callback: Callable[[str, str], None] | None = None,
) -> tuple[ChatMessage, GroundedAnswer]:
    """Run the document agent for one user message and persist the assistant turn.

    Returns the persisted ChatMessage (with citations attached) and the raw
    GroundedAnswer for callers that want to stream it incrementally.

    `status_callback(stage, message)` — if given — is invoked (synchronously,
    possibly from a worker thread if an agent tool is running) with
    human-readable progress updates as the turn proceeds, so a caller
    streaming this turn to a client can surface what's happening while it
    waits (see api/chat.py's `/chat/stream`).
    """
    deps = DocumentAgentDeps(
        user_id=str(user_id),
        thread_id=str(thread_id),
        db=db,
        retriever=retriever or _default_retriever(),
        allowed_org_ids=get_user_org_ids(db, user_id),
        on_status=status_callback,
    )

    turn_started = time.perf_counter()
    logger.info("[thread %s] turn started: %r", thread_id, user_message)

    if status_callback:
        status_callback("analyzing", "Analyzing your question...")
    agent_started = time.perf_counter()
    result = await document_agent.run(user_message, deps=deps)
    agent_elapsed = time.perf_counter() - agent_started
    answer = result.output
    logger.info(
        "[thread %s] document_agent.run() took %.2fs (%d unique chunk(s) retrieved across all tool calls)",
        thread_id,
        agent_elapsed,
        len(deps.retrieved_chunk_ids),
    )

    if status_callback:
        status_callback("validating", "Checking citations against retrieved passages...")
    validate_citations(answer, deps.retrieved_chunk_ids)

    message = chats.create_message(
        db,
        thread_id,
        "assistant",
        answer.answer,
        metadata={"has_sufficient_evidence": answer.has_sufficient_evidence},
    )
    chats.create_citations(
        db,
        message.id,
        [
            CitationInput(
                chunk_id=citation.chunk_id,
                quote_text=citation.quote_text,
                page_number=citation.page_number,
                section_label=citation.section_label,
            )
            for citation in answer.citations
        ],
    )
    logger.info(
        "[thread %s] turn finished in %.2fs total (%d citation(s), has_sufficient_evidence=%s)",
        thread_id,
        time.perf_counter() - turn_started,
        len(answer.citations),
        answer.has_sufficient_evidence,
    )
    return message, answer


ChatTurnRunner = Callable[
    ..., Awaitable[tuple[ChatMessage, GroundedAnswer]]
]  # (db, thread_id, user_id, user_message, *, status_callback=None) -> (message, answer)


def get_chat_turn_runner() -> ChatTurnRunner:
    """FastAPI dependency provider — overridable in tests, like get_db/get_current_user."""
    return run_chat_turn
