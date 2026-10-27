# Document Copilot Backend

FastAPI backend for authentication, document retrieval, and grounded chat. The backend owns privileged Supabase access and never exposes the service-role key to the browser.

## Requirements

- Python 3.12 or newer
- uv
- A configured Supabase project
- Direct Supabase database connection string for migrations

## Configuration

Create `backend/.env` from `.env.example`:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-public-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-secret-key
DATABASE_URL=postgresql://postgres:your-password@db.your-project-ref.supabase.co:5432/postgres
MISTRAL_API_KEY=your-mistral-api-key
MISTRAL_EMBEDDING_MODEL=mistral-embed
MISTRAL_EMBEDDING_DIMENSIONS=1024
ALLOWED_ORIGINS=http://localhost:5173
```

Use the direct/session database connection for Alembic. Do not use the transaction pooler URL. Keep `.env` out of source control.

The env vars above are the required ones. Everything else — the chat model (`MISTRAL_CHAT_MODEL`, default `mistral-small-latest`), retrieval tuning (`RETRIEVAL_TOP_K`, `RETRIEVAL_CANDIDATE_K`, ...), request timeouts, chat turn timeout, typing-effect pacing, heartbeat interval — has a sensible default in `app/config.py` and only needs an env var if you want to override it.

## Install and run

From `backend/`:

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

Useful URLs:

- OpenAPI documentation: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Database migration

Apply the current Alembic migration from `backend/`:

```powershell
uv run alembic upgrade head
```

Review migrations before applying them to a shared or production database.

## Current API

### Health check

`GET /health` is public and does not require authentication:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "document-copilot-backend"
}
```

### Current user

`GET /me` requires a Supabase access token:

```powershell
$token = "your-supabase-access-token"
Invoke-RestMethod http://localhost:8000/me -Headers @{ Authorization = "Bearer $token" }
```

Missing, empty, invalid, or expired bearer tokens return `401 Unauthorized`. Authentication is resolved before the protected route handler executes.

The dependency is defined in `app/auth/dependencies.py` and exposed to routes through `Depends(get_current_user)`.

### Chat API

All routes below (`app/api/chat.py`) require the same bearer token as `/me`, and every thread is scoped to its owning user (`403` if another user's thread is requested).

| Route | Description |
| ----- | ----------- |
| `POST /chat/threads` | Create a conversation. Body: `{"title": "optional title"}`. |
| `GET /chat/threads` | List the caller's conversations, most recently updated first. |
| `GET /chat/threads/{thread_id}/messages` | List a conversation's messages, each with its citations (enriched with ticker/filing type/date/title/source URL). |
| `POST /chat/stream` | Ask a question and stream the answer. Body: `{"threadId": "...", "messages": [...]}` (the last user message is used; earlier ones are for AI SDK client-side history). Response is `text/event-stream`. |

`/chat/stream`'s event sequence — see `app/chat/streaming.py` for the exact formatters:

```text
event: status         { "stage": "search", "message": "Searching filings for AAPL..." }   (repeats)
event: status         { "stage": "working", "message": "Still working on your answer..." } (heartbeat, ~every 6s if genuinely idle)
event: text_delta     { "text": "..." }                                                     (repeats — the typed-out answer)
event: citations      { "citations": [{ "chunk_id", "quote_text", "page_number", "section_label", "ticker", "filing_type", "filing_date", "document_title", "source_url" }] }
event: error          { "message": "..." }                                                  (grounding failure, timeout, or unexpected error — terminal)
event: done           {}                                                                    (terminal, success)
```

If the client disconnects mid-stream (e.g. the user clicks Stop), the in-flight agent turn is cancelled server-side rather than left running — see `app/api/chat.py`'s explicit `request.is_disconnected()` poll.

## Pipeline

One turn end to end: retrieve → agent → validate → persist → stream. For a
full file-by-file narrative of a single turn (frontend submit through to the
citation chip on screen), see [docs/pipeline.md](../docs/pipeline.md).

- **Retrieval** (`app/retrieval/`) — hybrid pgvector + Postgres full-text search fused with Reciprocal Rank Fusion. Full design, settings, and known limitations: [app/retrieval/README.md](app/retrieval/README.md).
- **Agent** (`app/assistant/`) — a PydanticAI agent (`document_agent`, Mistral `mistral-small-latest`) with typed tools (`search_filings`, `read_chunk`, `read_surrounding_chunks`) and a structured `GroundedAnswer` output. Product contract lives in `app/assistant/instructions.md`.
- **Grounding** (`app/grounding/`) — every citation is checked against what the agent actually retrieved this turn, enforced in code (fail closed). Full design: [app/grounding/README.md](app/grounding/README.md).
- **Orchestration** (`app/chat/orchestrator.py`, `app/api/chat.py`) — ties the above together for one turn, streams progress over SSE, and persists the result.

Tunable knobs (retrieval `top_k`/`candidate_k`, Mistral timeouts, chat turn timeout, typing-effect pacing, heartbeat interval) all live as fields on `Settings` in `app/config.py` — override any of them via `.env` without touching code. See the retrieval README's settings table for the retrieval-specific ones.

### Watching a turn happen

The backend logs detailed, timestamped tracing for every chat turn — useful for seeing exactly where time goes, or diagnosing a stuck/slow request. With the server running, watch its terminal output while asking a question:

```text
2026-09-14 10:15:02 [INFO] app.api.chat: [thread ...] /chat/stream received: 'Tell me about AMZN'
2026-09-14 10:15:03 [INFO] app.assistant.agent: [thread ...] [search] Searching filings for AMZN...
2026-09-14 10:15:05 [INFO] app.assistant.agent: [thread ...] search_filings(query=..., ticker='AMZN') took 1.82s, found 8 passage(s)
2026-09-14 10:15:12 [INFO] app.chat.orchestrator: [thread ...] document_agent.run() took 9.41s (8 unique chunk(s) retrieved across all tool calls)
2026-09-14 10:15:12 [INFO] app.chat.orchestrator: [thread ...] turn finished in 9.53s total (3 citation(s), has_sufficient_evidence=True)
2026-09-14 10:15:12 [INFO] app.api.chat: [thread ...] stream finished, 9.61s from request received to done
```

### Manual smoke tests

`scripts/smoke_retrieval.py` (retrieval only, cheap — one Mistral embedding call) and `scripts/smoke_assistant.py` (full agent turn, more expensive — drives a real chat completion) run the pipeline directly against the real corpus without a running API server, logging PASS/FAIL grounding checks. Both hit the real Mistral API and real Supabase database — don't loop them or run them casually; see the docstring at the top of each for details.

## Supabase user creation

For this internal application, public signup may remain disabled. Create users from Supabase Dashboard > Authentication > Users > Add user, then have them sign in through the frontend.

## Organization access

Users only retrieve documents of organizations they belong to (see [Access Control](../docs/architecture.md#access-control)). After a user has signed in once, grant access from `backend/`:

```powershell
uv run python scripts/manage_orgs.py create-org amazon "Amazon"
uv run python scripts/manage_orgs.py add-member an@amazon.com amazon
uv run python scripts/manage_orgs.py remove-member an@amazon.com amazon
uv run python scripts/manage_orgs.py list
```

Documents are assigned to an organization when imported with `../data/ingest_documents.py --org <slug>` (see [data/README.md](../data/README.md)). The smoke scripts search across every organization.

Never add a public user-creation endpoint that exposes the service-role key.

## Validation

```powershell
uv run ruff check app
uv run pytest -m "not integration"
```

Integration checks require live Supabase credentials and are marked separately.
