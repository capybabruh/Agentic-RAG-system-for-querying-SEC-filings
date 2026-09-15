from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase_auth.types import UserResponse

from app.api.chat import router as chat_router
from app.auth.dependencies import get_current_user
from app.config import settings

# No logging was configured anywhere in this app — Python's root logger defaults to
# WARNING with no console handler, so every logger.info(...) call across the codebase
# (turn timing, tool-call timing, status/heartbeat tracing — see app/api/chat.py,
# app/chat/orchestrator.py, app/assistant/agent.py) was being silently dropped. This is
# what actually makes that tracing visible in the terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Document Copilot backend API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/me", response_model=UserResponse)
async def current_user(
    user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    return user


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


