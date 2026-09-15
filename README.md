# Document Copilot

An internal AI chatbot that lets analysts query a corpus of documents in plain English and get sourced, citable answers.

## The client

**Driftwood Capital** — fictional independent investment research firm. Their analysts spend half their week reading 10-Ks and 10-Qs before they can produce any original analysis. Document Copilot eats that intake work so they can skip straight to insight.

Full brief: [docs/client-brief.md](docs/client-brief.md)

## Stack

| Layer              | Choice                                               |
| ------------------ | ---------------------------------------------------- |
| Backend            | Python + FastAPI                                     |
| Frontend           | Vite + React SPA + TypeScript                        |
| Database           | Supabase Postgres (users, chats, documents, chunks)  |
| Migrations         | SQLAlchemy models + Alembic                          |
| Retrieval          | Supabase `pgvector` + Postgres full-text search, fused with Reciprocal Rank Fusion |
| Agent              | PydanticAI (typed tools + grounded structured output) |
| Auth               | Supabase Auth (email only)                           |
| Hosting            | Railway                                              |
| LLM + embeddings   | Mistral AI (`mistral-small-latest` + `mistral-embed`) |

## How it works

One question, end to end:

1. **Retrieve** — the question is embedded and searched two ways in parallel (pgvector semantic search + Postgres full-text search over a Mistral-extracted keyword set), fused with Reciprocal Rank Fusion. See [backend/app/retrieval/README.md](backend/app/retrieval/README.md).
2. **Answer** — a PydanticAI agent (`document_agent`, Mistral) calls typed tools (`search_filings`, `read_chunk`, `read_surrounding_chunks`) to gather passages, then produces a structured `GroundedAnswer` (answer text + citations + a confidence flag).
3. **Validate** — every citation is checked against what the agent actually retrieved this turn; an answer claiming confidence with no citations, or citing something never retrieved, is rejected before it ever reaches the user. This is enforced in code, not just prompted. See [backend/app/grounding/README.md](backend/app/grounding/README.md).
4. **Stream** — the answer types out over SSE with live status updates ("Searching filings for AAPL...") while the agent works, then a cited, markdown-formatted answer.

Full file-by-file walkthrough of a single turn, start to finish: [docs/pipeline.md](docs/pipeline.md).

## Repo layout

```text
document-copilot/
├── AGENTS.md           # agent instructions (read first)
├── README.md           # this file
├── data/               # local corpus + download/ingestion scripts (payloads gitignored)
├── docs/
│   ├── client-brief.md # the client one-pager
│   ├── architecture.md # system design, retrieval strategy, grounding policy
│   ├── todo.md          # phase-by-phase build log, what's shipped and how it was verified
│   └── guides/          # first-time setup guides (Supabase, backend, frontend)
├── backend/            # FastAPI service — retrieval, agent, grounding, chat API
└── frontend/           # React SPA (Vite) — chat UI, sidebar, citations
```

## Prerequisites

Install these before setting up `backend/` or `frontend/`:

| Tool | Version | Used for | Install |
| ---- | ------- | -------- | ------- |
| [Python](https://www.python.org/downloads/) | 3.12+ | Backend runtime | OS package manager or python.org |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest | Backend deps + `data/download.py` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) | 20+ (LTS) | Frontend toolchain | nodejs.org or `nvm install --lts` |
| [pnpm](https://pnpm.io/installation) | latest | Frontend package manager | `corepack enable && corepack prepare pnpm@latest --activate` |

You also need accounts/keys for external services: start with [docs/guides/supabase-setup.md](docs/guides/supabase-setup.md) (account + project), then create a [Mistral AI API key](https://console.mistral.ai/api-keys) — the app uses Mistral for both chat generation and embeddings, no OpenAI dependency.

## Running locally

The app is fully built and runnable end to end (see [docs/todo.md](docs/todo.md) for what's shipped). Once both `.env` files are configured (see [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md)) and a corpus is ingested (see [Sample SEC data](#sample-sec-data) below), run both halves in separate terminals:

```bash
# terminal 1 — backend, http://localhost:8000
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# terminal 2 — frontend, http://localhost:5173
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173`, sign in, and ask a question about the ingested filings — you'll see live status updates while the agent searches, a typed-out cited answer, and clickable citation chips linking back to the source passage.

### Run with Docker instead

For local dev without installing Python/uv/Node/pnpm yourself, once both
`.env` files exist (same requirement as above — Docker doesn't change what
goes in them; both services still talk to your existing hosted Supabase
project, no database runs in Docker):

```bash
docker compose up --build
```

First time (or after a schema change), apply migrations inside the backend
container before or alongside `up`:

```bash
docker compose run --rm backend uv run alembic upgrade head
```

Both services hot-reload on file changes the same as running them natively.
This is a local-dev convenience only — Railway deployment uses its own
buildpack, unaffected by any of this (see
[docs/guides/railway-deploy.md](docs/guides/railway-deploy.md)).

First-time setup guides:

- [Supabase](docs/guides/supabase-setup.md) — account, hosted project (dashboard or CLI)
- [Backend](docs/guides/backend-setup.md) — how the backend was bootstrapped (Alembic, package layout, Jupyter kernel)
- [Frontend](docs/guides/frontend-setup.md) — how the frontend was bootstrapped (Vite, shadcn)
- [Railway deployment](docs/guides/railway-deploy.md) — deploying the backend + frontend as two Railway services

## Sample SEC data

Use the standalone downloader to fetch a small local 10-K sample from SEC EDGAR.
Edit the params at the top of `data/download.py`, especially `USER_AGENT`, then run:

```bash
uv run data/download.py
```

By default this downloads the latest 5 10-K filings for AAPL, MSFT, NVDA, AMZN, and GOOGL into year folders under `data/downloads/` and writes a `manifest.json`.
Downloaded files are gitignored; the `data/` folder itself stays in git for the script and notes.

From there, converting to Markdown, importing into Supabase, and chunking + embedding are separate steps — see [data/README.md](data/README.md) for the full ingestion pipeline.
