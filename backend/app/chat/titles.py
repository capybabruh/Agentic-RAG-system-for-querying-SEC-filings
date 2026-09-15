"""Deriving a thread title from its first user message.

New threads are created with no title (frontend/src/components/chat/ThreadSidebar.tsx
falls back to "New conversation" in the UI until then); the first message of a turn
gives us something more useful to show in the sidebar.
"""
from __future__ import annotations

import re

_MAX_TITLE_LENGTH = 60


def derive_thread_title(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= _MAX_TITLE_LENGTH:
        return collapsed

    truncated = collapsed[:_MAX_TITLE_LENGTH]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:!?") + "…"
