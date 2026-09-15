from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from supabase_auth.types import UserResponse

from app.auth.dependencies import get_current_user
from app.chat.orchestrator import ChatTurnRunner, get_chat_turn_runner
from app.chat.schemas import (
    ChatStreamRequest,
    CitationResponse,
    MessageResponse,
    ThreadCreate,
    ThreadResponse,
)
from app.chat.streaming import (
    format_citations,
    format_done,
    format_error,
    format_status,
    format_text_delta,
    format_thread_title,
)
from app.chat.titles import derive_thread_title
from app.config import settings
from app.database import chats
from app.database.session import get_db
from app.database.users import get_or_create_user
from app.grounding.validator import GroundingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])
DbSession = Annotated[Session, Depends(get_db)]
AuthenticatedUser = Annotated[UserResponse, Depends(get_current_user)]
ChatTurnRunnerDep = Annotated[ChatTurnRunner, Depends(get_chat_turn_runner)]


@router.get("/threads", response_model=list[ThreadResponse])
async def list_chat_threads(auth_user: AuthenticatedUser, db: DbSession) -> list[ThreadResponse]:
    user = get_or_create_user(db, auth_user)
    threads = chats.list_threads(db, user.id)
    db.commit()
    return threads


@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_thread(
    payload: ThreadCreate,
    auth_user: AuthenticatedUser,
    db: DbSession,
) -> ThreadResponse:
    user = get_or_create_user(db, auth_user)
    thread = chats.create_thread(db, user.id, payload.title)
    db.commit()
    db.refresh(thread)
    return thread


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_thread(
    thread_id: uuid.UUID,
    auth_user: AuthenticatedUser,
    db: DbSession,
) -> None:
    thread = require_owned_thread(db, thread_id, auth_user)
    chats.delete_thread(db, thread)
    db.commit()


@router.get("/threads/{thread_id}/messages", response_model=list[MessageResponse])
async def get_chat_messages(
    thread_id: uuid.UUID,
    auth_user: AuthenticatedUser,
    db: DbSession,
) -> list[MessageResponse]:
    thread = require_owned_thread(db, thread_id, auth_user)
    return chats.list_messages(db, thread.id)


def require_owned_thread(
    db: Session,
    thread_id: uuid.UUID,
    auth_user: UserResponse,
):
    user = get_or_create_user(db, auth_user)
    thread = chats.get_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Thread access denied")
    return thread


@router.post("/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    auth_user: AuthenticatedUser,
    db: DbSession,
    run_turn: ChatTurnRunnerDep,
    request: Request,
) -> StreamingResponse:
    thread = require_owned_thread(db, payload.thread_id, auth_user)
    latest_user_message = next(
        (message for message in reversed(payload.messages) if message.role == "user"),
        None,
    )
    if latest_user_message is None or not latest_user_message.text().strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one non-empty user message is required",
        )

    user_content = latest_user_message.text().strip()
    logger.info("[thread %s] /chat/stream received: %r", thread.id, user_content)
    chats.create_message(db, thread.id, "user", user_content)

    # Untitled threads (every thread starts this way — see ThreadCreate) pick up a
    # title from their first message so the sidebar shows something more useful than
    # a generic "New conversation" placeholder.
    new_title: str | None = None
    if thread.title is None:
        new_title = derive_thread_title(user_content)
        thread.title = new_title

    db.commit()

    async def generate() -> AsyncIterator[str]:
        stream_started = time.perf_counter()
        if new_title is not None:
            yield format_thread_title(new_title)
        loop = asyncio.get_running_loop()
        status_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def on_status(stage: str, message: str) -> None:
            loop.call_soon_threadsafe(status_queue.put_nowait, (stage, message))

        task = asyncio.create_task(
            run_turn(db, thread.id, thread.user_id, user_content, status_callback=on_status)
        )
        deadline = loop.time() + settings.chat_turn_timeout_seconds
        last_status_at = loop.time()

        try:
            try:
                while not task.done():
                    # Relying on the generator's own cancellation/GC to notice a dropped
                    # client (e.g. via the `finally` below) isn't reliable in practice —
                    # Starlette only discovers a broken connection the next time it tries
                    # to *send* a chunk, and our generator can go a while between yields
                    # (up to chat_heartbeat_interval_seconds). Poll the ASGI disconnect
                    # signal explicitly instead so a dropped client (e.g. clicking Stop)
                    # is detected promptly rather than leaving the turn to keep running
                    # (and spending Mistral calls) in the background.
                    if await request.is_disconnected():
                        task.cancel()
                        logger.info(
                            "Client disconnected from thread %s stream; cancelling in-flight turn",
                            thread.id,
                        )
                        return
                    if loop.time() >= deadline:
                        task.cancel()
                        logger.warning(
                            "Chat turn for thread %s exceeded %ss, aborting",
                            thread.id,
                            settings.chat_turn_timeout_seconds,
                        )
                        db.rollback()
                        yield format_error("The assistant took too long to respond. Please try again.")
                        return
                    try:
                        stage, message = await asyncio.wait_for(status_queue.get(), timeout=0.5)
                        yield format_status(stage, message)
                        last_status_at = loop.time()
                    except asyncio.TimeoutError:
                        # The agent's own status callbacks only fire around tool calls — the final
                        # answer-generation call (often the slowest single step, since it drafts
                        # prose and structures citations at once) can run for a while with no
                        # callback in between. Without this, the status line goes silent and the
                        # turn looks stalled/dead even though it's still working. Ping every
                        # ~heartbeat_interval_seconds while genuinely idle so it stays visibly alive.
                        if loop.time() - last_status_at >= settings.chat_heartbeat_interval_seconds:
                            elapsed = time.perf_counter() - stream_started
                            logger.info(
                                "[thread %s] heartbeat — still waiting on the agent, %.1fs elapsed so far",
                                thread.id,
                                elapsed,
                            )
                            yield format_status("working", "Still working on your answer...")
                            last_status_at = loop.time()
                        continue
                while not status_queue.empty():
                    stage, message = status_queue.get_nowait()
                    yield format_status(stage, message)

                message_row, answer = await task
                db.commit()
            except GroundingError:
                db.rollback()
                yield format_error("The answer could not be grounded in retrieved passages.")
                return
            except Exception:
                db.rollback()
                logger.exception("Chat turn failed for thread %s", thread.id)
                yield format_error("Something went wrong while generating the answer. Please try again.")
                return

            # Batched into small word-groups rather than one SSE event per word — each
            # event triggers a re-render (and, via MessageList, a full markdown re-parse
            # of the accumulated text) on the client, so one-event-per-word means hundreds
            # of renders in a few seconds for a long answer, enough to visibly lag the tab.
            words = answer.answer.split(" ")
            chunk_size = max(1, settings.chat_typing_chunk_words)
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i : i + chunk_size])
                yield format_text_delta(chunk + " ")
                if settings.chat_typing_delay_seconds > 0:
                    await asyncio.sleep(settings.chat_typing_delay_seconds)

            citations = [
                CitationResponse.model_validate(citation)
                for citation in chats.get_message_citations(db, message_row.id)
            ]
            yield format_citations(citations)
            yield format_done()
            logger.info(
                "[thread %s] stream finished, %.2fs from request received to done",
                thread.id,
                time.perf_counter() - stream_started,
            )
        finally:
            # Backstop for any exit path not covered by the explicit is_disconnected()
            # check above (e.g. a disconnect during the text_delta/citations phase, or
            # this generator being torn down for some other reason) — make sure we never
            # leave the agent task running unattended.
            if not task.done():
                logger.info("Client disconnected from thread %s stream; cancelling in-flight turn", thread.id)
                task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
