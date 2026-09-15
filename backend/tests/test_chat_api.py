from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from supabase_auth.types import User, UserResponse

from app.api import chat as chat_api
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import get_current_user
from app.chat.orchestrator import get_chat_turn_runner
from app.chat.schemas import AiSdkMessage, ChatStreamRequest, MessagePart
from app.database import chats
from app.database.base import Base
from app.database.models import ChatMessage, ChatThread, MessageCitation
from app.database.models import User as AppUser
from app.database.session import get_db
from app.main import app


async def fake_run_chat_turn(
    db: Session,
    thread_id: UUID,
    user_id: UUID,
    user_message: str,
    status_callback: Callable[[str, str], None] | None = None,
):
    # Keeps this test fast and network-free (no real OpenAI/Mistral calls) per AGENTS.md —
    # the agent/retrieval/grounding contract itself is covered under tests/assistant,
    # tests/retrieval, and tests/grounding. Exercises the status_callback path the real
    # /chat/stream generate() always wires up, without needing a real agent run.
    if status_callback:
        status_callback("analyzing", "Analyzing your question...")
    answer = GroundedAnswer(answer="Mocked grounded answer.", citations=[], has_sufficient_evidence=False)
    message = chats.create_message(
        db,
        thread_id,
        "assistant",
        answer.answer,
        metadata={"has_sufficient_evidence": answer.has_sufficient_evidence},
    )
    return message, answer


async def fake_failing_run_chat_turn(
    db: Session,
    thread_id: UUID,
    user_id: UUID,
    user_message: str,
    status_callback: Callable[[str, str], None] | None = None,
):
    # Simulates an unexpected failure deep in the agent/retrieval stack (e.g. a Mistral
    # timeout) to verify generate() surfaces it as a clean SSE error event instead of
    # silently dying (the bug this test guards against).
    if status_callback:
        status_callback("search", "Searching filings...")
    raise RuntimeError("simulated retrieval failure")


def make_auth_user(user_id: UUID, email: str) -> UserResponse:
    return UserResponse(
        user=User(
            id=str(user_id),
            app_metadata={},
            user_metadata={},
            aud="authenticated",
            email=email,
            created_at=datetime.now(UTC),
        )
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[AppUser.__table__, ChatThread.__table__, ChatMessage.__table__, MessageCitation.__table__],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    current_auth_user = make_auth_user(uuid4(), "analyst@example.com")

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_auth() -> UserResponse:
        return current_auth_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_chat_turn_runner] = lambda: fake_run_chat_turn
    with TestClient(app) as test_client:
        test_client.current_auth_user = current_auth_user  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_create_list_and_stream_thread(client: TestClient) -> None:
    create_response = client.post("/chat/threads", json={"title": "Annual filings"})
    assert create_response.status_code == 201
    thread_id = create_response.json()["id"]

    list_response = client.get("/chat/threads")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == thread_id

    stream_response = client.post(
        "/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [
                {
                    "id": "message-1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "What changed?"}],
                }
            ],
        },
    )
    assert stream_response.status_code == 200
    assert "event: status" in stream_response.text
    assert "event: text_delta" in stream_response.text
    assert "event: citations" in stream_response.text
    assert "event: done" in stream_response.text

    messages_response = client.get(f"/chat/threads/{thread_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [message["sender"] for message in messages] == ["user", "assistant"]
    assistant_message = messages[1]
    assert assistant_message["message_metadata"] == {"has_sufficient_evidence": False}
    assert assistant_message["citations"] == []


def test_stream_titles_an_untitled_thread_from_the_first_message(client: TestClient) -> None:
    create_response = client.post("/chat/threads", json={})
    thread_id = create_response.json()["id"]
    assert create_response.json()["title"] is None

    stream_response = client.post(
        "/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [
                {
                    "id": "message-1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "What changed in the latest 10-K?"}],
                }
            ],
        },
    )
    assert stream_response.status_code == 200
    assert 'event: thread_title\ndata: {"title": "What changed in the latest 10-K?"}' in stream_response.text

    list_response = client.get("/chat/threads")
    assert list_response.json()[0]["title"] == "What changed in the latest 10-K?"


def test_stream_does_not_retitle_an_already_titled_thread(client: TestClient) -> None:
    create_response = client.post("/chat/threads", json={"title": "Annual filings"})
    thread_id = create_response.json()["id"]

    stream_response = client.post(
        "/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [
                {"id": "message-1", "role": "user", "parts": [{"type": "text", "text": "What changed?"}]}
            ],
        },
    )
    assert stream_response.status_code == 200
    assert "event: thread_title" not in stream_response.text

    list_response = client.get("/chat/threads")
    assert list_response.json()[0]["title"] == "Annual filings"


def test_stream_surfaces_unexpected_errors_as_sse_error_event(client: TestClient) -> None:
    create_response = client.post("/chat/threads", json={"title": "Annual filings"})
    thread_id = create_response.json()["id"]

    app.dependency_overrides[get_chat_turn_runner] = lambda: fake_failing_run_chat_turn

    stream_response = client.post(
        "/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [
                {"id": "message-1", "role": "user", "parts": [{"type": "text", "text": "What changed?"}]}
            ],
        },
    )

    assert stream_response.status_code == 200
    assert "event: status" in stream_response.text
    assert "event: error" in stream_response.text
    assert "Something went wrong" in stream_response.text
    assert "event: done" not in stream_response.text

    messages_response = client.get(f"/chat/threads/{thread_id}/messages")
    assert messages_response.status_code == 200
    # Only the user's message persisted — the failed turn wrote no assistant message.
    assert [message["sender"] for message in messages_response.json()] == ["user"]


def test_stream_sends_heartbeat_status_during_silent_gaps(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Guards against the real bug reported live: the agent's own status callbacks only
    # fire around tool calls, so the (often slowest) final answer-generation step can run
    # for a while with no callback — without a heartbeat, the status line goes silent and
    # the turn looks stalled/dead even though it's still working.
    monkeypatch.setattr(chat_api.settings, "chat_heartbeat_interval_seconds", 0.05)

    async def fake_slow_silent_run_chat_turn(
        db: Session,
        thread_id: UUID,
        user_id: UUID,
        user_message: str,
        status_callback: Callable[[str, str], None] | None = None,
    ):
        # No status_callback calls at all — simulates the silent final-generation gap.
        await asyncio.sleep(0.6)
        answer = GroundedAnswer(answer="Answer after a silent gap.", citations=[], has_sufficient_evidence=True)
        message = chats.create_message(db, thread_id, "assistant", answer.answer)
        return message, answer

    create_response = client.post("/chat/threads", json={"title": "Annual filings"})
    thread_id = create_response.json()["id"]
    app.dependency_overrides[get_chat_turn_runner] = lambda: fake_slow_silent_run_chat_turn

    stream_response = client.post(
        "/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [
                {"id": "message-1", "role": "user", "parts": [{"type": "text", "text": "What changed?"}]}
            ],
        },
    )

    assert stream_response.status_code == 200
    assert '"stage": "working"' in stream_response.text
    assert "Still working" in stream_response.text
    assert "event: done" in stream_response.text


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeDisconnectingRequest:
    """Reports connected on the first check, disconnected on every check after —
    simulates a client that drops mid-stream (e.g. clicking Stop) partway through."""

    def __init__(self) -> None:
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls > 1


@pytest.mark.anyio
async def test_generate_cancels_backend_task_when_client_disconnects(client: TestClient) -> None:
    # Guards against the bug reported live: clicking "Stop" only aborted the client's
    # connection, but the backend kept running the agent turn (and spending Mistral calls)
    # in the background regardless, later silently persisting an answer nobody asked to
    # keep waiting for. An earlier version of this fix relied on Starlette's generator
    # cleanup (`finally` running when the generator is closed/GC'd) to notice a dropped
    # client — that turned out to be unreliable in the real request path (Starlette only
    # discovers a broken connection the next time it tries to *send* a chunk, which our
    # generator may not attempt for a while), so this exercises the real fix: an explicit
    # `request.is_disconnected()` poll inside the loop. Starlette's own TestClient can't
    # simulate a genuine mid-stream disconnect (its fake `receive()` only ever reports
    # "http.disconnect" *after* the response has already fully completed — see
    # starlette/testclient.py), so this calls `stream_chat` directly with a fake `Request`
    # that reports disconnected after the first check.
    cancelled = asyncio.Event()

    async def fake_slow_run_chat_turn(
        db: Session,
        thread_id: UUID,
        user_id: UUID,
        user_message: str,
        status_callback: Callable[[str, str], None] | None = None,
    ):
        if status_callback:
            status_callback("search", "Searching filings...")
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        answer = GroundedAnswer(answer="Should never get here.", citations=[], has_sufficient_evidence=True)
        message = chats.create_message(db, thread_id, "assistant", answer.answer)
        return message, answer

    create_response = client.post("/chat/threads", json={"title": "Annual filings"})
    thread_id = UUID(create_response.json()["id"])
    auth_user = client.current_auth_user  # type: ignore[attr-defined]

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)

    payload = ChatStreamRequest(
        thread_id=thread_id,
        messages=[AiSdkMessage(role="user", parts=[MessagePart(type="text", text="What changed?")])],
    )

    streaming_response = await chat_api.stream_chat(
        payload=payload,
        auth_user=auth_user,
        db=db,
        run_turn=fake_slow_run_chat_turn,
        request=FakeDisconnectingRequest(),  # type: ignore[arg-type]
    )

    generator = streaming_response.body_iterator
    await generator.__anext__()  # first loop iteration: connected, yields the "search" status
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()  # second iteration: is_disconnected() now True, generator returns

    await asyncio.wait_for(cancelled.wait(), timeout=1.0)

    messages = chats.list_messages(db, thread_id)
    # Only the user's message persisted — the cancelled turn never wrote an assistant reply.
    assert [message.sender for message in messages] == ["user"]


def test_delete_thread_removes_it_from_the_list(client: TestClient) -> None:
    create_response = client.post("/chat/threads", json={"title": "Annual filings"})
    thread_id = create_response.json()["id"]

    delete_response = client.delete(f"/chat/threads/{thread_id}")
    assert delete_response.status_code == 204

    list_response = client.get("/chat/threads")
    assert list_response.json() == []

    messages_response = client.get(f"/chat/threads/{thread_id}/messages")
    assert messages_response.status_code == 404


def test_user_cannot_delete_another_users_thread(client: TestClient) -> None:
    owner_id = client.current_auth_user.user.id  # type: ignore[attr-defined]
    thread_id = uuid4()

    db_override = app.dependency_overrides[get_db]
    db_generator = db_override()
    db = next(db_generator)
    db.add(AppUser(id=UUID(owner_id), email="owner@example.com"))
    db.add(ChatThread(id=thread_id, user_id=UUID(owner_id), title="Private"))
    db.commit()
    db.close()

    other_user = make_auth_user(uuid4(), "other@example.com")
    app.dependency_overrides[get_current_user] = lambda: other_user

    response = client.delete(f"/chat/threads/{thread_id}")
    assert response.status_code == 403
    assert response.json()["detail"] == "Thread access denied"


def test_user_cannot_access_another_users_thread(client: TestClient) -> None:
    owner_id = client.current_auth_user.user.id  # type: ignore[attr-defined]
    thread_id = uuid4()

    db_override = app.dependency_overrides[get_db]
    db_generator = db_override()
    db = next(db_generator)
    db.add(AppUser(id=UUID(owner_id), email="owner@example.com"))
    db.add(ChatThread(id=thread_id, user_id=UUID(owner_id), title="Private"))
    db.commit()
    db.close()

    other_user = make_auth_user(uuid4(), "other@example.com")
    app.dependency_overrides[get_current_user] = lambda: other_user

    response = client.get(f"/chat/threads/{thread_id}/messages")
    assert response.status_code == 403
    assert response.json()["detail"] == "Thread access denied"


def test_missing_token_is_rejected() -> None:
    with TestClient(app) as test_client:
        response = test_client.get("/chat/threads")
    assert response.status_code == 401
