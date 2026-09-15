# Local development image — see the repo root README.md's "Run with Docker" section.
# Not used for Railway deployment (Railway builds this service directly from
# pyproject.toml/uv.lock via its own buildpack — see docs/guides/railway-deploy.md).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Dependency layers first so `uv sync` is cached across rebuilds that only
# change application code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--reload"]
