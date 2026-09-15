"""Extracts 3-5 keyword terms from a natural-language query for the full-text
search stage, via a cheap Mistral chat completion.

Fails open: any error or empty extraction falls back to the raw query rather
than breaking retrieval — this is a best-effort optimization of the
full-text branch, not the grounding path.
"""
from __future__ import annotations

import logging

from mistralai.client import Mistral

from app.config import settings

logger = logging.getLogger(__name__)

_PROMPT = (
    "Extract 3 to 5 keyword terms from the question below, for a full-text "
    "keyword search. Keep multi-word proper nouns or phrases together "
    '(e.g. "Data Center", "revenue mix"). Drop question words and filler. '
    "Return ONLY the terms, comma-separated, nothing else.\n\nQuestion: {query}"
)


def extract_keywords(client: Mistral, model: str, query: str) -> str:
    try:
        response = client.chat.complete(
            model=model,
            messages=[{"role": "user", "content": _PROMPT.format(query=query)}],
            temperature=0.0,
            max_tokens=40,
            timeout_ms=settings.retrieval_keyword_extraction_timeout_ms,
        )
        content = response.choices[0].message.content.strip()
        terms = [term.strip() for term in content.split(",") if term.strip()]
        if terms:
            return " ".join(terms)
    except Exception:
        logger.warning("keyword extraction failed, falling back to raw query", exc_info=True)
    return query
