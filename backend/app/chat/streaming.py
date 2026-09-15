"""SSE event formatting for the chat stream.

Pure formatting only — no DB, no agent calls — so the wire shape stays
independently testable from the request-scoped persistence/error handling in
api/chat.py. This is a custom `text_delta`/`status`/`citations`/`error`/`done`
event contract, not the literal Vercel AI SDK data-stream protocol —
frontend/src/chat/transport.ts translates it into AI SDK UIMessageChunks
(status/citations are handled out-of-band via callbacks/REST refetch rather
than as stream chunks; see backend/app/grounding/README.md and
backend/app/retrieval/README.md for the pipeline this reports on).
"""
from __future__ import annotations

import json

from app.chat.schemas import CitationResponse


def format_text_delta(text: str) -> str:
    return f"event: text_delta\ndata: {json.dumps({'text': text})}\n\n"


def format_citations(citations: list[CitationResponse]) -> str:
    payload = [citation.model_dump(mode="json") for citation in citations]
    return f"event: citations\ndata: {json.dumps({'citations': payload})}\n\n"


def format_status(stage: str, message: str) -> str:
    return f"event: status\ndata: {json.dumps({'stage': stage, 'message': message})}\n\n"


def format_thread_title(title: str) -> str:
    return f"event: thread_title\ndata: {json.dumps({'title': title})}\n\n"


def format_error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'message': message})}\n\n"


def format_done() -> str:
    return "event: done\ndata: {}\n\n"
