# Railway deployment

This app deploys as two Railway services from one GitHub repo — a FastAPI backend and a static Vite frontend build — talking to the same hosted Supabase project you already set up for local dev (see [Supabase setup](supabase-setup.md)). This matches the target shape in [docs/architecture.md](../architecture.md#deployment-shape): Railway stays stateless, Supabase holds every durable record (users, chats, documents, chunks, embeddings, citations).

```text
GitHub repo
├── backend/   →  Railway service "backend"   (FastAPI + Uvicorn)
└── frontend/  →  Railway service "frontend"  (Vite build, served statically)
                          both talk to the same Supabase project + Mistral API
```

## Prerequisites

- The repo pushed to GitHub (Railway deploys from a GitHub connection, not a local push).
- A working Supabase project with migrations already applied — if you followed [Supabase setup](supabase-setup.md) and [Backend setup](backend-setup.md) for local dev, this is already done and you don't need to run migrations again (it's the same database).
- A Mistral API key.
- Your local `backend/.env` and `frontend/.env` open in front of you — you'll copy most of these values into Railway.

## 1. Create a Railway account and project

1. Go to [railway.com](https://railway.com) and sign up (GitHub login is easiest — it's also what you'll use to import the repo).
2. New accounts get a one-time **$5 Trial credit** for 30 days, after which unused projects fall back to the Free plan ($1/month of credit — enough to idle, not enough to run two always-on services for a full month). For anything beyond a demo, plan to add a card and move to the **Hobby plan** ($5/month base, includes $5 of usage) from Railway's pricing page.
3. Click **New Project** → **Deploy from GitHub repo** → pick this repository. Authorize Railway's GitHub app if prompted.
4. Railway will try to auto-detect a service from the repo root. Since this is a monorepo with no code at the root, delete that first auto-created service (or leave it and rename it once you retarget its root directory below) — you'll create the two real services explicitly next.

## 2. Deploy the backend service

1. In the project, **New** → **GitHub Repo** → select the same repo again (each service is its own connection to the repo, scoped to a subdirectory).
2. Open the new service's **Settings** tab:
   - **Root Directory** → `backend`. This tells Railway to build only from that subfolder — it also means later commits that only touch `frontend/` won't redeploy this service.
   - Rename the service to `backend` (top of Settings) so it's easy to reference from the frontend later.
3. Railway's builder (Railpack) detects `pyproject.toml` + `uv.lock` and installs with `uv` automatically — no build command needed. It does **not** know how to start a FastAPI app on its own, so under **Settings → Deploy → Start Command**, set:

   ```text
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

   `$PORT` is injected by Railway at runtime and changes per deploy — always bind to it rather than a hardcoded port. If the deploy log shows `uvicorn: command not found`, prefix the command with `uv run` (`uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`) — that forces it to run inside the `uv`-managed virtualenv explicitly.
4. Still in Settings, set **Deploy → Healthcheck Path** to `/health`. Railway uses this to know a deploy actually came up before routing traffic to it, and to auto-restart it if it later stops responding.
5. Go to the **Variables** tab and add (values from your local `backend/.env` — see [backend README](../../backend/README.md#configuration) for what each one does):

   | Variable | Value |
   | -------- | ----- |
   | `SUPABASE_URL` | same as local |
   | `SUPABASE_ANON_KEY` | same as local |
   | `SUPABASE_SERVICE_ROLE_KEY` | same as local — never put this in the frontend service |
   | `DATABASE_URL` | same direct/session Supabase connection string used for Alembic locally |
   | `MISTRAL_API_KEY` | same as local |
   | `ALLOWED_ORIGINS` | placeholder for now — `http://localhost:5173`. You'll replace this with the real frontend URL in step 4 |

   Everything else (`MISTRAL_CHAT_MODEL`, retrieval tuning, timeouts, ...) has a default in `app/config.py` and only needs a Railway variable if you want to override it.
6. Go to **Settings → Networking** and click **Generate Domain**. Note the `*.up.railway.app` URL — you'll need it for the frontend.
7. Trigger a deploy (it likely already started when you added the service). Watch the **Deployments** tab; once it's live, confirm from your own machine:

   ```bash
   curl https://<your-backend>.up.railway.app/health
   ```

   Expect `{"status":"ok","service":"document-copilot-backend"}`.

## 3. Deploy the frontend service

1. Back in the project, **New** → **GitHub Repo** → same repo again.
2. **Settings → Root Directory** → `frontend`. Rename the service to `frontend`.
3. Railpack detects the Node/pnpm project and runs `pnpm install` then `pnpm run build` automatically (that's the existing `build` script — `tsc -b && vite build`). It still needs to be told how to *serve* the built files, so set **Settings → Deploy → Start Command** to:

   ```text
   pnpm exec vite preview --host 0.0.0.0 --port $PORT
   ```

   `vite preview` serves the `dist/` folder produced by the build step. Its default `appType: "spa"` behavior serves `index.html` for any unknown path, which is what makes deep links like `/app/thread/<id>` work on a hard refresh instead of 404ing — you don't need a separate static-file server or extra config for that.
4. **Variables** tab — this is the part that trips people up: Vite bakes `VITE_*` variables into the JS bundle **at build time**, not read at runtime. Any time you change one of these, you need a new deploy (not just a restart) for it to take effect.

   | Variable | Value |
   | -------- | ----- |
   | `VITE_API_BASE_URL` | `https://${{backend.RAILWAY_PUBLIC_DOMAIN}}` — a Railway reference variable that resolves to the backend service's domain from step 2. Using a reference instead of pasting the URL means it updates automatically if the backend's domain ever changes |
   | `VITE_SUPABASE_URL` | same as local |
   | `VITE_SUPABASE_ANON_KEY` | same as local — this is the public key, safe here (never put `SUPABASE_SERVICE_ROLE_KEY` in this service) |

5. **Settings → Networking** → **Generate Domain**. This is the URL your analysts will actually open.
6. Deploy, then open the generated URL in a browser — you should land on `/login`.

## 4. Wire the two services together

The backend's `ALLOWED_ORIGINS` is still pointing at `localhost` from step 2, so the browser's requests from the real frontend domain will be blocked by CORS. Fix it now that you know the frontend's real URL:

1. Backend service → **Variables** → set `ALLOWED_ORIGINS` to `https://<your-frontend>.up.railway.app` (comma-separate multiple origins if you also want to keep `http://localhost:5173` working for local dev against the prod backend — most people don't).
2. Save — Railway redeploys the backend automatically on a variable change.
3. Reload the frontend URL and try signing in. If you see a CORS error in the browser console mentioning "blocked by CORS policy", double check this value matches the frontend's origin exactly (scheme + host, no trailing slash, no path).

## 5. Verify end to end

1. Open the frontend URL, sign in (or sign up — see the note on public signup in [backend README](../../backend/README.md#supabase-user-creation) if you've disabled it).
2. Create a conversation and ask a question about an ingested filing. This exercises the full path: Supabase auth → `/chat/stream` → Mistral → Supabase Postgres → SSE back to the browser.
3. Try the delete-conversation button (trash icon on hover in the sidebar) — confirm the dialog appears, cancel, then confirm-delete, and check the thread disappears.
4. If nothing answers, check the backend's **Deployments → View Logs** in Railway — the app logs detailed per-turn tracing (see [backend README](../../backend/README.md#watching-a-turn-happen)) that shows exactly where a turn is stuck or failing.

## Ongoing deploys

Once connected, Railway redeploys a service automatically on every push to the branch you connected (default: your repo's default branch) that touches files under that service's **Root Directory**. No extra CI config needed. Each service's **Deployments** tab keeps prior deploys around, and **Settings → Deploy** has a "Redeploy" / rollback action if a push breaks something.

## Troubleshooting

| Symptom | Likely cause |
| ------- | ------------ |
| Frontend loads but every request fails with a CORS error | `ALLOWED_ORIGINS` on the backend doesn't exactly match the frontend's origin (step 4) |
| Refreshing `/app/thread/<id>` shows a blank page or 404 | Start command isn't `vite preview` (or a custom static server without SPA fallback) — see step 3.3 |
| Backend deploy log ends with `uvicorn: command not found` | Prefix the start command with `uv run` |
| Frontend still calling `localhost:8000` after deploying | `VITE_*` vars are baked at build time — changing them requires a new deploy, not just a restart |
| `401 Unauthorized` on every request | `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` on the frontend, or `SUPABASE_URL` / keys on the backend, don't match the same Supabase project |
| Backend healthcheck never goes green | Healthcheck Path isn't set to `/health`, or `DATABASE_URL` / `MISTRAL_API_KEY` is missing so the app fails on startup — check deploy logs |

## Next steps

- [Supabase setup](supabase-setup.md) — the hosted database and auth both services depend on
- [Backend setup](backend-setup.md) — env vars, migrations, local run
- [Frontend setup](frontend-setup.md) — env vars, local run
