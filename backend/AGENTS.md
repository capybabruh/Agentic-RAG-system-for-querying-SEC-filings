# Backend — agent notes

This is the FastAPI service for Document Copilot. Read [../AGENTS.md](../AGENTS.md) first — universal building rules live there. This file adds backend-specific conventions.

## Stack

- Python 3.12+
- FastAPI + uvicorn
- Pydantic v2 + pydantic-settings
- `httpx` for outbound HTTP
- `pytest` for tests
- Supabase Python client (DB + auth)
- SQLAlchemy models + Alembic migrations for database schema changes
- Mistral SDK for both LLM generation (`mistral-small-latest`) and embeddings (`mistral-embed`, 1024 dimensions) — no OpenAI dependency; `document_chunks.embedding` is `vector(1024)`
- Supabase `pgvector` for semantic search and Postgres full-text search for keyword retrieval. Hybrid search should run vector and full-text queries separately, then fuse ranked results in Python with Reciprocal Rank Fusion.
- `structlog` for logging
- `uv` for dependency + project management

## Dependency policy

See universal policy in [../AGENTS.md](../AGENTS.md). Backend-specific:

- **Prefer stdlib:** `pathlib`, `datetime`, `uuid`, `enum`, `dataclasses`, `asyncio`, `collections`, `itertools`, `json`, `urllib`.
- **Not OK without justification:** `python-dateutil`, `toolz`, `funcy`, `more-itertools`, small JSON/string micro-libs, "ergonomic" wrappers on top of declared SDKs.
- Dev deps (test/lint/build) have a looser bar but still pick widely-used, low-footprint tools (`pytest`, `ruff`, `httpx`).

## Layout (to be created during build)

```text
backend/
├── alembic/
│   ├── env.py           # Imports app database metadata for autogenerate
│   └── versions/        # Reviewed migration files
├── alembic.ini
├── app/
│   ├── main.py          # FastAPI entrypoint
│   ├── config.py        # Pydantic settings — single source of truth for env
│   ├── api/             # FastAPI routers (chat, ingest, auth)
│   ├── auth/            # Supabase JWT verification + current user dependency
│   ├── chat/            # turn orchestration, AI SDK message conversion, streaming
│   ├── assistant/       # PydanticAI agent, deps, outputs, instructions
│   ├── retrieval/       # pgvector/full-text queries, RRF fusion, source passage lookup
│   ├── grounding/       # citation validation and answer grounding checks
│   ├── database/        # SQLAlchemy models, Supabase client wrapper, typed query helpers
│   └── prompts/         # prompt/instruction templates if not colocated with assistant
├── ingest/              # one-off ingestion scripts (Markdown extraction, chunking, embedding, Supabase writes)
├── tests/
└── pyproject.toml
```

## Code style (backend-specific)

- **Type hints on public functions and module-level things.** Don't annotate every local.
- **Async by default in request-path code.** Don't run blocking I/O on the event loop. Tempfile + small synchronous file reads are OK (they're fast); network calls must be async.
- **Use `async def` for all route handlers** and any I/O service function.
- **Validate at boundaries only.** HTTP input is validated by Pydantic models. External API responses are validated when parsed. Internal callers are trusted.

## Configuration

- `app.config.settings` is the single source of truth. Import settings where needed; never call `os.getenv` in app code, never call `load_dotenv`.
- If a third-party SDK reads `os.environ` directly, add the mirror in `config.py` — don't sprinkle `setdefault` elsewhere.
- Fail fast on startup when required env vars are missing.

## Database migrations

- Alembic is the source of truth for schema changes. Do not change production tables manually in the Supabase dashboard.
- SQLAlchemy models describe normal tables and columns. Alembic autogenerate creates candidate migrations, but every generated migration must be reviewed before applying.
- Supabase/Postgres-specific features belong in explicit migration operations: `create extension vector`, generated `tsvector` columns, HNSW/GIN indexes, RLS enablement, and RLS policies.
- Alembic must use the direct/session database connection, not the Supabase transaction pooler URL.
- Run migrations from `backend/` with `uv run alembic upgrade head`.

## Tests

- **Prefer unit over integration.** Mock at the service boundary.
- Fast suite (`pytest -m "not integration"`) must stay green and hit no network / no DB.
- Integration tests go behind `@pytest.mark.integration` and may require live Mistral / Supabase credentials.
- Tests live next to what they test (`retrieval/retriever.py` → `tests/retrieval/test_retriever.py`).
- Required test coverage: ingestion logic, retrieval, citation extraction, grounding enforcement.

## Anti-patterns (rejected)

- `os.getenv` / `load_dotenv` in modules.
- Wrapping FastAPI responses in custom envelope classes.
- Over-catching `Exception` just to log and re-raise; let it propagate.
- Shared state through globals instead of FastAPI `app.state` or DI.
- Silent fallbacks that hide real config errors.
- Mocking the LLM in unit tests without also testing the grounding contract — the prompt is the product.
