# Document Copilot Architecture

## Purpose

Document Copilot is an internal research assistant for analysts who need grounded answers from a curated SEC filing corpus. The architecture must optimize for trust: every answer is generated from retrieved source passages, every factual claim is citable, and the system fails clearly when the corpus does not support an answer.

This document describes the target architecture for the chat experience, LLM orchestration, and the communication layer between the React SPA, Supabase, and FastAPI backend.

## High-Level Architecture

The best opening diagram is a service-level view that shows the two core paths: the live chat path that serves users, and the ingestion path that prepares SEC filings for retrieval.

```mermaid
flowchart LR
    user[Analyst] --> browser[Browser<br/>React chat app]

    subgraph railway[Railway]
        frontend[Frontend service<br/>Vite build]
        backend[Backend service<br/>FastAPI + PydanticAI]
    end

    subgraph supabase[Supabase]
        auth[Auth<br/>email session]
        db[(Postgres<br/>chats, documents, chunks<br/>organizations + members<br/>pgvector + full-text)]
    end

    mistral[Mistral<br/>LLM generation + embeddings]
    corpus[SEC filing corpus]
    ingestion[Ingestion pipeline<br/>download, parse, chunk, embed]
    admin[Admin CLI<br/>manage_orgs.py]

    frontend -->|serves app| browser
    browser -->|sign in| auth
    auth -->|JWT session| browser
    browser -->|chat request + JWT| backend
    backend -->|verify user| auth
    backend -->|retrieve passages<br/>persist chats + citations| db
    backend -->|generate grounded answer<br/>embed query| mistral
    backend -->|stream answer + citations| browser

    corpus --> ingestion
    ingestion -->|create embeddings| mistral
    ingestion -->|store documents + chunks<br/>tagged with org_id| db
    admin -->|organizations + memberships| db
```

## Architectural Goals

- Keep the browser thin: it renders chat state, manages the user's Supabase session, and streams assistant responses.
- Keep the backend authoritative: retrieval, grounding, citation checks, tool execution, and database writes happen in FastAPI.
- Use Supabase for identity and durable product state: users, organizations and their members, chat threads, source documents, chunks, embeddings, and citation metadata.
- Scope every document read to the requesting user's organizations, enforced by the backend and never decided by the model (see [Access Control](#access-control)).
- Use Supabase `pgvector` for semantic retrieval and Postgres full-text search for keyword retrieval.
- Make the LLM path typed and testable by using PydanticAI agents with explicit dependencies, outputs, and tool boundaries.
- Preserve a simple deployment model on Railway: one frontend service, one stateless backend service, and hosted Supabase.

## Stack

Frontend:

- Vite + React SPA + TypeScript
- React Router for routing
- Tailwind CSS and shadcn/ui for UI
- `@supabase/supabase-js` for browser auth
- Vercel AI SDK UI packages for chat state and streaming client behavior

Backend:

- Python 3.12+
- FastAPI + Uvicorn
- Pydantic v2 + pydantic-settings
- PydanticAI for typed LLM orchestration
- Mistral SDK for both generation (`mistral-small-latest`) and embeddings (`mistral-embed`, 1024 dimensions) — no OpenAI dependency
- Supabase Python client for server-side database access
- SQLAlchemy models + Alembic migrations for schema management
- Supabase `pgvector` for semantic search
- Postgres full-text search for lexical retrieval
- `httpx` for outbound HTTP
- `structlog` for structured logs

Persistence:

- Supabase Auth for email login
- Supabase Postgres for user records, chat threads, chat messages, source documents, chunks, embeddings, full-text search vectors, and citation metadata

## System Boundaries

The frontend is responsible for user interaction, local UI state, and sending the authenticated user's request to the backend. It should never hold service-role credentials, run retrieval logic, call the LLM/embedding provider directly, or write privileged records to Supabase.

The backend is responsible for request authorization, retrieval, prompt construction, LLM execution, citation validation, streaming responses, and durable persistence. It owns all privileged credentials and is the only service allowed to use the Supabase service-role key.

Supabase is responsible for authentication and durable product state. Browser access uses the anon key and user JWT. Server access uses either the user's bearer token for user-scoped operations or the service-role key for privileged writes that must still be explicitly tied to the authenticated user.

## Request Flow

1. The user signs in with Supabase email auth in the React SPA.
2. The frontend stores the Supabase session through `@supabase/supabase-js`.
3. When the user opens a chat, the frontend loads the thread and prior messages through FastAPI, which reads user-scoped records from Supabase.
4. The chat UI uses the Vercel AI SDK React primitives to manage message state and submit new user messages to the FastAPI chat endpoint.
5. The frontend sends the Supabase access token as `Authorization: Bearer <token>`.
6. FastAPI verifies the token with Supabase Auth before doing any retrieval or LLM work.
7. FastAPI resolves the user's organizations from `organization_members` and creates a request-scoped context containing the authenticated user, chat thread, allowed organization IDs, database session, retrieval service, and status callback.
8. A PydanticAI agent retrieves relevant document chunks, generates a grounded answer, and returns typed output containing answer text and citations.
9. FastAPI streams assistant message parts back to the browser in the format expected by the AI SDK client.
10. FastAPI persists the final user message, assistant message, cited chunks, and usage metadata to Supabase.

## Frontend Chat Layer

The frontend remains a plain Vite SPA. It should not adopt Next.js route handlers or server components. The AI SDK is used only for its React chat primitives and streaming client behavior.

The chat module should be organized around these responsibilities:

- `src/lib/env.ts` validates `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`.
- `src/lib/supabase.ts` creates the browser Supabase client.
- `src/lib/http.ts` wraps `fetch`, applies the backend base URL, injects the Supabase bearer token, handles timeouts, and converts failures into typed API errors.
- `src/lib/api.ts` exposes product-level calls such as loading threads, creating threads, and fetching message history.
- `src/pages/chat/*` renders chat routes and delegates chat streaming to a focused chat component.
- `src/components/chat/*` renders messages, citations, source passages, empty states, and streaming status.

The chat component should initialize with stored messages and then let the AI SDK manage in-flight UI state. The transport points to FastAPI, not to a frontend server route.

Conceptual shape:

```ts
const { messages, sendMessage, status, error } = useChat({
  id: threadId,
  messages: initialMessages,
  transport: new DefaultChatTransport({
    api: `${apiBaseUrl}/chat/stream`,
    headers: async () => ({
      Authorization: `Bearer ${await getAccessToken()}`,
    }),
  }),
});
```

The exact API surface should be verified during implementation against the installed AI SDK version. The architectural rule is stable: the browser streams to FastAPI with the user's Supabase token, and FastAPI owns the assistant run.

## Backend LLM Layer

PydanticAI should be introduced as the backend's orchestration layer for answer generation. It replaces ad hoc prompt calls with a typed agent boundary.

Recommended backend modules:

```text
backend/app/
├── api/
│   └── chat.py                 # FastAPI routes for chat threads and streaming
├── auth/
│   └── dependencies.py         # Supabase JWT verification and current user dependency
├── chat/
│   ├── orchestrator.py         # Coordinates one chat turn end-to-end
│   ├── messages.py             # Converts AI SDK messages to and from internal message types
│   └── streaming.py            # Emits AI SDK-compatible streaming events
├── assistant/
│   ├── agent.py                # PydanticAI agent definition
│   ├── deps.py                 # Runtime dependency dataclass for the agent
│   ├── outputs.py              # GroundedAnswer, Citation, and SourcePassage
│   └── instructions.md         # System instructions and product contract
├── retrieval/
│   ├── queries.py              # pgvector and full-text SQL queries
│   ├── fusion.py               # Reciprocal Rank Fusion for hybrid search
│   └── retriever.py            # Query-to-source-passage retrieval logic
├── grounding/
│   └── validator.py            # Ensures citations map to retrieved passages
└── database/
    ├── supabase.py             # Supabase client construction
    ├── models.py               # SQLAlchemy table models used by Alembic autogenerate
    ├── chats.py                # Chat, thread, message, and citation persistence
    └── documents.py            # Source document, chunk, embedding, and search queries
```

These names should follow the product workflow rather than a generic service layer. `chat/orchestrator.py` owns the full turn lifecycle, `assistant/agent.py` owns the LLM boundary, `retrieval/` owns hybrid source-passage search, and `grounding/` owns the trust contract that answers must cite retrieved evidence.

The agent should receive explicit dependencies rather than reaching into globals:

```python
@dataclass
class DocumentAgentDeps:
    user_id: str
    thread_id: str
    db: Session
    retriever: DocumentRetriever
    allowed_org_ids: list[uuid.UUID]  # resolved by the backend, never by the model
    retrieved_chunk_ids: set[uuid.UUID]  # filled by tools, checked by grounding


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    cited_passages: list[SourcePassage]
```

The agent's instructions should encode the product contract:

- Answer only from retrieved passages.
- Cite every factual claim.
- If the retrieved context is insufficient, say that the corpus does not contain enough evidence.
- Do not provide stock recommendations or investment advice.
- Keep answers concise enough for analyst review, but include enough cited passages to verify the answer.

Retrieval and grounding remain independent from PydanticAI. This keeps ingestion, retrieval tests, and citation validation testable without invoking the LLM.

## Retrieval Strategy

Document Copilot uses hybrid retrieval:

1. Embed the user's query with the configured Mistral embedding model (the same model used at ingestion time, so query and stored vectors are comparable).
2. Run a semantic search over `document_chunks.embedding` with `pgvector`.
3. Run a lexical search over `document_chunks.search_vector` with Postgres full-text search.
4. Fuse the two ranked lists in Python with Reciprocal Rank Fusion.
5. Fetch the selected chunks, source document metadata, and optional neighboring chunks for grounding.

This keeps the database responsible for efficient ranked retrieval and keeps the application responsible for product-specific ranking policy. The first implementation should avoid agent-generated SQL; the PydanticAI agent receives bounded tools such as `search_filings`, `read_chunk`, and `read_surrounding_chunks`.

Both ranked queries, the passage hydration step, and neighbor reads are scoped to the caller's organizations with `source_documents.org_id`, so ranking only ever happens over documents the user may read.

## Access Control

Document Copilot is a shared corpus with per-organization visibility: an Amazon analyst retrieves only Amazon's filings, a Meta analyst only Meta's. All organizations share one database; isolation is a row-level `org_id` filter applied by the backend on every read path, not separate databases or schemas.

### Three checks per request

| Layer | Question it answers | Mechanism | Failure |
| --- | --- | --- | --- |
| Authentication | Who is this? | Supabase Auth JWT, verified by `get_current_user` on every request | `401` |
| Chat ownership | Is this your thread? | `chat_threads.user_id` checked by `require_owned_thread` | `403` |
| Document scope | Which documents may you read? | `organization_members` → `allowed_org_ids` → `source_documents.org_id` filter in every retrieval query | Empty results; the agent reports insufficient evidence |

### Data model

```mermaid
erDiagram
    users ||--o{ organization_members : "belongs to"
    organizations ||--o{ organization_members : has
    organizations ||--o{ source_documents : owns
    source_documents ||--o{ document_chunks : "split into"
    users ||--o{ chat_threads : owns

    organizations {
        uuid id PK
        string slug "unique, e.g. amazon"
        string name
    }
    organization_members {
        uuid org_id PK
        uuid user_id PK
        string role "member by default"
    }
    source_documents {
        uuid id PK
        uuid org_id FK "NULL = visible to nobody"
        string company_ticker
    }
```

- A user can belong to several organizations (composite key `org_id, user_id`); an auditor covering two companies gets two membership rows.
- Only `source_documents` carries `org_id`. Chunks inherit it through `source_document_id`, so re-tagging a document never requires re-embedding.
- Deleting an organization cascades to its memberships and documents.

### Request path

```mermaid
sequenceDiagram
    actor An as An (Amazon analyst)
    participant API as FastAPI
    participant LLM as Mistral agent
    participant DB as Postgres

    An->>API: POST /chat/stream + JWT
    API->>API: verify JWT, check thread ownership
    API->>DB: SELECT org_id FROM organization_members WHERE user_id = An
    DB-->>API: [amazon]
    API->>LLM: question + tool definitions (no org parameter)
    LLM-->>API: call search_filings(query, ticker)
    API->>DB: hybrid search WHERE d.org_id = ANY([amazon])
    DB-->>API: Amazon passages only
    API->>LLM: tool result
    LLM-->>API: GroundedAnswer + citations
    API->>API: validate citations against retrieved chunk IDs
    API-->>An: stream answer citing Amazon filings
```

The model never touches the database. It only proposes tool arguments (`query`, `ticker`, `filing_type`, `chunk_id`); the backend executes the tool with `allowed_org_ids` taken from `DocumentAgentDeps`. If the model asks for `ticker="META"` on An's behalf, the query still carries `org_id = ANY([amazon])` and returns nothing. A guessed `chunk_id` from another organization is filtered the same way in `read_chunk` and `read_surrounding_chunks`.

### Enforcement points

| Where | What it enforces |
| --- | --- |
| `app/database/organizations.py::get_user_org_ids` | Resolves the user's organizations from `organization_members` |
| `app/chat/orchestrator.py::run_chat_turn` | Puts the resolved IDs into `DocumentAgentDeps.allowed_org_ids` for the turn |
| `app/assistant/agent.py` | All three tools pass `ctx.deps.allowed_org_ids` through; none exposes an org parameter to the model (covered by a test) |
| `app/retrieval/queries.py` | `vector_search` and `fulltext_search` add `d.org_id = ANY(:allowed_org_ids)` |
| `app/retrieval/retriever.py` | `_load_passages` and `read_surrounding_chunks` filter on `SourceDocument.org_id`; an empty list returns nothing without calling Mistral |

Policy is deny-by-default: a user with no memberships, or a document with `org_id IS NULL`, matches nothing.

### Administration

Access is managed by an admin from the backend, not self-served in the app.

```bash
# from backend/
uv run python scripts/manage_orgs.py create-org amazon "Amazon"
uv run python scripts/manage_orgs.py add-member an@amazon.com amazon     # user must have signed in once
uv run python scripts/manage_orgs.py remove-member an@amazon.com amazon
uv run python scripts/manage_orgs.py list                                # members, document counts, untagged documents

# assign documents while importing (--org is required, --ticker optional)
uv run python ../data/ingest_documents.py --org amazon --ticker AMZN
# tag documents that were imported before organizations existed (no re-embedding)
uv run python ../data/ingest_documents.py --org amazon --ticker AMZN --update
```

The importer refuses to run when the organization does not exist, so a typo cannot silently create untagged or mis-tagged documents. Organization membership is never read from Supabase `user_metadata`, which users can edit themselves.

### Rollout

Migration `20261028_000003` adds the tables and a nullable `org_id`. Until existing documents are tagged, nobody can retrieve them, so apply the migration, create organizations, re-run the importer with `--update` per ticker, then add members — in that order.

### Known gaps

- **No RLS yet.** The tables live in Supabase's `public` schema without row-level security, so the browser-visible anon key can reach them through Supabase's Data API. The backend's own filter does not cover that path. Enabling RLS on every table (no policies are needed while the browser never queries tables directly) is the next step; policies keyed on `auth.uid()` would add database-level defense in depth.
- **Backend connects as a privileged role**, so correctness of the `org_id` filter depends on application code and its tests.
- **`org_id` is nullable** until the corpus is backfilled; a follow-up migration can make it `NOT NULL`.
- **Filtered HNSW search** may return fewer than `retrieval_candidate_k` vector candidates for small organizations; pgvector 0.8's `hnsw.iterative_scan` addresses this.
- **No in-app upload or roles beyond `member`.** Uploads would take `org_id` from the uploader's membership, never from client input.

## Supabase and FastAPI Communication

Supabase Auth is the identity source. FastAPI must treat the browser's Supabase JWT as the request credential.

Frontend rules:

- Use the anon key only in the browser.
- Read the current session through the shared Supabase client.
- Send the access token to FastAPI through the shared API client.
- Never pass tokens through component props.
- Never expose the service-role key to the frontend.

Backend rules:

- Verify `Authorization: Bearer <token>` at the FastAPI boundary.
- Reject unauthenticated requests before retrieval or LLM work.
- Derive `user_id` and email from the verified Supabase user.
- Derive document scope from `organization_members` for that `user_id`; never accept an organization from the request body or from model output.
- Use user-scoped database operations wherever possible.
- Use the service-role key only on the backend for privileged writes that cannot be safely performed with the anon key.
- Always attach persisted chat records to the authenticated `user_id`.

The backend can verify the JWT by calling Supabase Auth's user endpoint or by validating the project's JWT signing keys. For the first implementation, calling Supabase Auth is simpler and avoids local JWT validation mistakes. If request volume grows, local JWT verification can be added behind the same `AuthService` interface.

Recommended backend units:

- `app/auth/dependencies.py` validates bearer tokens and exposes `get_current_user`.
- `app/database/supabase.py` creates user-scoped and admin Supabase clients.
- `app/database/chats.py` stores and reads chat threads, messages, and citation records.
- `app/database/documents.py` stores and reads source documents, chunks, embeddings, and full-text search data.

## Streaming Contract

The frontend should receive incremental assistant output, not wait for a full answer. FastAPI should expose a streaming endpoint that emits AI SDK-compatible message parts.

Recommended endpoint:

```text
POST /chat/stream
Authorization: Bearer <supabase_access_token>
Content-Type: application/json
```

Request body:

```json
{
  "threadId": "uuid",
  "messages": []
}
```

The `messages` payload should use the AI SDK UI message format at the frontend boundary. FastAPI can translate that wire format into internal Pydantic models before invoking the agent.

Streaming responsibilities:

- Send text deltas as the answer is generated.
- Send citation/source metadata as structured parts once available.
- Send clear error events for authentication failures, missing threads, retrieval failures, and grounding failures.
- Persist only after the assistant run completes successfully, unless a separate partial-message model is deliberately introduced later.

## Data Model

Supabase tables should be small and product-oriented:

- `profiles`: one row per authenticated user, keyed by Supabase `auth.users.id`.
- `chat_threads`: thread metadata, owner, title, timestamps.
- `chat_messages`: user and assistant messages in order, with AI SDK-compatible message JSON where useful.
- `message_citations`: normalized citation records linked to assistant messages.
- `organizations`: tenants that own documents, keyed by a unique slug such as `amazon`.
- `organization_members`: which users may read which organization's documents, with a role.
- `source_documents`: original document records with owning `org_id`, filing metadata, source URL, and normalized Markdown content.
- `document_chunks`: chunk text, chunk metadata, embeddings, and generated full-text search vectors.

`source_documents` stores the normalized Markdown version of each filing so the application can re-chunk, inspect, and cite the original extracted text without reaching back into downloaded HTML files. `document_chunks` stores retrieval-ready passages:

- chunk ID
- document ID
- chunk index
- page or section metadata
- chunk text
- embedding vector
- generated `tsvector` for full-text search
- token count
- metadata JSON for ticker, company, filing type, filing date, year, accession number, page, section, and source offsets

Hybrid retrieval runs two bounded queries against `document_chunks`: a semantic `pgvector` query and a Postgres full-text query. The backend fuses those ranked lists with Reciprocal Rank Fusion, then fetches the selected chunks and neighboring context for grounding.

## Schema Management

Database schema changes are managed from the backend with SQLAlchemy models and Alembic migrations. Supabase is the hosted Postgres database, but the Supabase dashboard is not the source of truth for table definitions.

The workflow is:

1. Update SQLAlchemy models in `app/database/models.py`.
2. Generate a candidate migration with `uv run alembic revision --autogenerate -m "<change>"`.
3. Review the generated migration file in `backend/alembic/versions/`.
4. Add explicit migration operations for Postgres/Supabase features that autogenerate cannot infer reliably.
5. Apply the migration locally or against the linked Supabase database with `uv run alembic upgrade head`.
6. Commit both the model changes and the migration file.

Normal tables and ordinary indexes should be represented in SQLAlchemy models where practical. The following should be written explicitly in migrations with `op.execute()` or carefully reviewed Alembic operations:

- `create extension if not exists vector`
- `vector(1024)` embedding columns if the SQLAlchemy type renderer is not sufficient
- generated `tsvector` columns
- HNSW indexes for vector search
- GIN indexes for full-text search and JSON metadata
- RLS enablement and policies
- grants or Supabase role-specific permissions

Alembic must connect with Supabase's direct/session database connection string. Do not run migrations through the transaction pooler URL, because schema migrations, extension setup, and index creation require session-level database behavior.

## Grounding and Citation Policy

Grounding is part of the architecture, not a prompt preference.

The backend should enforce these invariants:

- Every assistant answer has at least one citation unless the answer explicitly says there is not enough evidence.
- Every citation maps to a retrieved source passage.
- Cited passages include enough metadata for the frontend to show company, filing, date, page or section, and excerpt.
- The model cannot cite documents that were not retrieved for the current request.
- If citation validation fails, the backend returns a controlled failure instead of a polished unsupported answer.

This policy should be covered by backend unit tests around retrieval, citation extraction, and grounding enforcement.

## Error Handling

Expected error classes:

- `401 Unauthorized`: missing, expired, or invalid Supabase token.
- `403 Forbidden`: authenticated user tries to access another user's thread.
- `404 Not Found`: thread or source document does not exist.
- `422 Unprocessable Entity`: invalid request payload.
- `502 Bad Gateway`: upstream LLM or Supabase failure.
- `500 Internal Server Error`: unexpected backend failure.

The frontend should render friendly messages while preserving enough technical detail in logs for debugging. Network and CORS failures should be distinguishable from HTTP failures in the shared API client.

## Configuration

Each service must keep one settings module as the source of truth.

Frontend settings:

- `VITE_API_BASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Backend settings:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `DATABASE_URL` for Alembic and direct Postgres access
- `MISTRAL_API_KEY`, chat model name, embedding model name, and embedding dimensions (LLM generation + embeddings both run on Mistral)
- `ALLOWED_ORIGINS`

Do not read environment variables directly from components, route handlers, or services. Frontend code should use `src/lib/env.ts`. Backend code should use `app/config.py`.

## Deployment Shape

Railway should run two services:

- Frontend: static Vite build served as a web app.
- Backend: FastAPI service running Uvicorn.

Supabase remains hosted and stores the durable retrieval data. The Railway backend can stay stateless because document chunks, embeddings, full-text search vectors, chats, and citations all live in Supabase Postgres. Raw downloaded filings remain gitignored local ingestion inputs unless a later workflow stores them in object storage.

## Implementation Sequence

1. Scaffold the frontend SPA and backend FastAPI app according to the repo conventions.
2. Add SQLAlchemy models and Alembic migration setup in the backend.
3. Add the initial Alembic migration for `pgvector`, source document, chunk, full-text, chat, and citation tables.
4. Add Supabase Auth in the frontend and token verification in FastAPI.
5. Add the shared frontend API client with automatic bearer-token injection.
6. Add the chat streaming endpoint with a stubbed assistant response.
7. Add AI SDK chat UI on the frontend pointed at FastAPI.
8. Add Markdown ingestion, chunking, embeddings, and Supabase writes.
9. Add semantic search with `pgvector`.
10. Add Postgres full-text search and Python RRF fusion.
11. Add PydanticAI document agent with typed dependencies and typed answer output.
12. Add citation validation and grounding enforcement.
13. Add final UI for citations, source passages, empty states, and errors.

## Non-Goals

- No Next.js, SSR, server components, or frontend route handlers.
- No direct LLM/embedding provider calls from the browser.
- No separate managed vector database outside Supabase.
- No per-tenant databases or schemas: organizations share one database and are isolated by `org_id` (see [Access Control](#access-control)).
- No external market/news data.
- No trading recommendations or generated stock picks.
