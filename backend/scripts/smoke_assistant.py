"""Smoke test for the full agent turn: retrieval + Mistral generation + grounding.

Requires a live Mistral key with available credits — generation and embeddings
both run on Mistral (no OpenAI dependency). More expensive than
scripts/smoke_retrieval.py (drives a full chat completion, not just an
embedding), so don't loop this or run it casually. Calls the real
document_agent against the real ingested corpus — does NOT persist anything to
chat_threads/chat_messages, so it's safe to run against the production
Supabase database.

Works from a plain terminal (`uv run python scripts/smoke_assistant.py`) or
from a Jupyter cell (`import scripts.smoke_assistant as sa; sa.SELECTED = [...]; await sa.main()`,
or `%run scripts/smoke_assistant.py`) — nest_asyncio lets asyncio.run() work
even though Jupyter already has its own event loop running. Logging (not
print) so the timestamped, per-question progress is visible either way.

Pick which question(s) run by setting SELECTED below. Multiple questions run
concurrently (each opens its own DB session, so there's no shared state
between them) — see the rate-limit note below before selecting many at once.
"""
from __future__ import annotations

import asyncio
import logging

import nest_asyncio
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy import select

from app.assistant.agent import document_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.chat.orchestrator import _default_retriever
from app.database.models import Organization
from app.database.session import SessionLocal
from app.grounding.validator import GroundingError, validate_citations

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
logger = logging.getLogger("smoke_assistant")

QUESTIONS = {
    "well_scoped": (
        "Across Apple's 2021-2025 10-Ks, how did the revenue mix between iPhone, "
        "Services, Mac, iPad, and Wearables change, and which category appears to "
        "have contributed most to any mix shift?"
    ),
    "out_of_scope": "What will Apple's stock price be next year?",
    "q10_generative_ai_margins": (
        "If an analyst asks whether the filings prove that generative AI improved "
        "margins for any of these companies, what evidence exists in the corpus, "
        "and where should the bot refuse to infer beyond the filings?"
    ),
    "custom": "Type any question here to try it.",
}

# List one or more keys from QUESTIONS above (or edit "custom" and include it).
# Mistral's free/low tier rate-limits aggressively — each question already makes
# several requests via the agent's tool-calling loop, so running many keys at once
# increases the odds of a 429. A single retry-with-backoff is built in below, but if
# you're seeing repeated failures, select fewer keys rather than raising retries.
SELECTED = ["out_of_scope"]

RETRY_DELAY_SECONDS = 15


async def run_one(key: str) -> None:
    question = QUESTIONS[key]
    logger.info("[%s] starting — Q: %s", key, question)

    with SessionLocal() as db:
        deps = DocumentAgentDeps(
            user_id="smoke-script",
            thread_id="smoke-script",
            db=db,
            retriever=_default_retriever(),
            # Admin smoke test: search across every organization's documents.
            allowed_org_ids=list(db.scalars(select(Organization.id))),
        )
        answer = await _run_with_retry(key, question, deps)

        logger.info("[%s] has_sufficient_evidence: %s", key, answer.has_sufficient_evidence)
        logger.info("[%s] answer: %s", key, answer.answer)
        logger.info("[%s] citations (%d):", key, len(answer.citations))
        for citation in answer.citations:
            logger.info(
                "[%s]   - chunk=%s section=%r quote=%r",
                key,
                citation.chunk_id,
                citation.section_label,
                citation.quote_text[:150],
            )

        try:
            validate_citations(answer, deps.retrieved_chunk_ids)
            logger.info("[%s] grounding check: PASS (every citation traces to a retrieved chunk)", key)
        except GroundingError as error:
            logger.error("[%s] grounding check: FAIL — %s", key, error)


async def _run_with_retry(key: str, question: str, deps: DocumentAgentDeps) -> GroundedAnswer:
    try:
        result = await document_agent.run(question, deps=deps)
        return result.output
    except ModelHTTPError as error:
        if error.status_code != 429:
            raise
        logger.warning("[%s] rate limited (429), retrying once in %ss", key, RETRY_DELAY_SECONDS)
        await asyncio.sleep(RETRY_DELAY_SECONDS)
        result = await document_agent.run(question, deps=deps)
        return result.output


async def main() -> None:
    logger.info("Running %d question(s) in parallel: %s", len(SELECTED), SELECTED)
    await asyncio.gather(*(run_one(key) for key in SELECTED))


if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
