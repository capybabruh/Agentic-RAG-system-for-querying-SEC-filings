# Document Copilot Frontend

Vite + React + TypeScript SPA for Document Copilot — a chat interface for asking questions about ingested SEC filings and getting cited, verifiable answers.

## Requirements

- Node.js 20 or newer
- pnpm
- A configured Supabase project
- The backend running at `http://localhost:8000`

## Configuration

Create `frontend/.env` from `.env.example`:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-public-key
```

Only public Supabase values belong in this file. Never add the Supabase service-role key here.

## Install and run

From `frontend/`:

```powershell
pnpm install
pnpm dev
```

Open `http://localhost:5173`.

Useful checks:

```powershell
pnpm tsc --noEmit
pnpm lint
pnpm build
```

## What's here

- `/login`, `/signup` — Supabase email/password auth. Public signup can remain disabled for this internal app (see backend README) — create users from the Supabase dashboard instead.
- `/app`, `/app/thread/:threadId` — the chat workspace, behind `ProtectedRoute` (redirects to `/login` if unauthenticated, and on any `401` from the backend).

The chat workspace (`src/pages/ChatPage.tsx`) is a sidebar + main pane layout built on shadcn's composable `Sidebar`:

- **Sidebar** (`src/components/chat/ThreadSidebar.tsx`) — collapses to an icon-only rail (state persisted automatically), a "New chat" button, the conversation list (active thread highlighted), and a footer with the signed-in user's avatar/email and a "Sign out" menu.
- **Chat session** (`src/components/chat/ChatSession.tsx`) — the message list, input box, and a footer status line. Asking a question streams: live status updates ("Searching filings for AAPL...", a heartbeat if the agent goes quiet, "Drafting your answer..." once text starts), an elapsed-time counter, a typed-out answer, then citation chips. A "Stop" button cancels the request (server-side too, not just the client connection).
- **Answers** (`src/components/chat/MessageList.tsx`, `Markdown.tsx`) — assistant text renders through `react-markdown` + `remark-gfm` (headings, bold, lists, tables, links), styled onto the app's design tokens. A "Limited evidence found in the corpus" badge appears when the agent couldn't fully answer from the filings.
- **Citations** (`src/components/chat/Citations.tsx`) — numbered chips under each assistant message; clicking one opens a popover with the ticker, filing type, date, section, the quoted excerpt, and a link to the original filing.

## Design system

`src/index.css` defines the app's tokens (Tailwind v4 `@theme`) — a light theme with one deliberate accent color (`--color-citation`, gold) reserved for citations, kept separate from `--color-primary` (buttons) so it stays the one thing that reads as "verified." shadcn/ui primitives live in `src/components/ui/`; add new ones with `pnpm dlx shadcn@latest add <name>` (see `AGENTS.md` — the CLI has a known Windows path-resolution bug that drops files under a stray `./@/` folder instead of `src/`, fix by moving them and correcting the `cn` import).

## Backend API check

The frontend expects the backend at `VITE_API_BASE_URL`. Check that it is available before testing login:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

After signing in, create a conversation from the sidebar and ask a question — that exercises the full round trip (auth token → `/chat/stream` → SSE → citations) end to end.
