# Local development image — see the repo root README.md's "Run with Docker" section.
# Not used for Railway deployment (Railway builds this service directly from
# package.json via its own buildpack — see docs/guides/railway-deploy.md).
FROM node:20-slim

WORKDIR /app

RUN corepack enable

# Dependency layer first so `pnpm install` is cached across rebuilds that
# only change application code.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173

# Vite's dev server only binds to localhost by default, which isn't
# reachable from outside the container without --host.
CMD ["pnpm", "dev", "--", "--host", "0.0.0.0"]
