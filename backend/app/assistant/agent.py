from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.config import settings
from app.retrieval.retriever import SourcePassage

logger = logging.getLogger(__name__)

INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8")

# Mistral for both generation and embeddings (no OpenAI credits available). Built
# explicitly (not via the "mistral:<model>" shorthand) so the API key comes from
# app.config.settings, not an ambient MISTRAL_API_KEY process env var — see AGENTS.md's
# "never read os.environ directly" rule.
document_agent = Agent(
    MistralModel(settings.mistral_chat_model, provider=MistralProvider(api_key=settings.mistral_api_key)),
    deps_type=DocumentAgentDeps,
    output_type=GroundedAnswer,
    instructions=INSTRUCTIONS,
)


def _remember(ctx: RunContext[DocumentAgentDeps], passages: list[SourcePassage]) -> list[SourcePassage]:
    ctx.deps.retrieved_chunk_ids.update(passage.chunk_id for passage in passages)
    return passages


def _status(ctx: RunContext[DocumentAgentDeps], stage: str, message: str) -> None:
    # Logged here (not just sent as an SSE status event) so the backend terminal shows a
    # live, timestamped trace of what the agent is doing — this is the tool's own decision
    # to act, not yet the actual work, which is timed separately below.
    logger.info("[thread %s] [%s] %s", ctx.deps.thread_id, stage, message)
    if ctx.deps.on_status:
        ctx.deps.on_status(stage, message)


@document_agent.tool
def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    ticker: str | None = None,
    filing_type: str | None = None,
) -> list[SourcePassage]:
    """Hybrid semantic + keyword search over ingested SEC filing chunks."""
    _status(ctx, "search", f"Searching filings{f' for {ticker}' if ticker else ''}...")
    started = time.perf_counter()
    with ctx.deps.db_lock:
        passages = ctx.deps.retriever.search(
            ctx.deps.db,
            query,
            ticker=ticker,
            filing_type=filing_type,
            allowed_org_ids=ctx.deps.allowed_org_ids,
        )
    elapsed = time.perf_counter() - started
    passages = _remember(ctx, passages)
    logger.info(
        "[thread %s] search_filings(query=%r, ticker=%r) took %.2fs, found %d passage(s)",
        ctx.deps.thread_id,
        query,
        ticker,
        elapsed,
        len(passages),
    )
    _status(ctx, "search_done", f"Found {len(passages)} matching passage(s)")
    return passages


@document_agent.tool
def read_chunk(ctx: RunContext[DocumentAgentDeps], chunk_id: uuid.UUID) -> SourcePassage | None:
    """Read a single previously-retrieved chunk by id, verbatim."""
    _status(ctx, "read_chunk", "Reading a specific passage...")
    started = time.perf_counter()
    with ctx.deps.db_lock:
        passages = ctx.deps.retriever.read_surrounding_chunks(
            ctx.deps.db, chunk_id, window=0, allowed_org_ids=ctx.deps.allowed_org_ids
        )
    elapsed = time.perf_counter() - started
    passages = _remember(ctx, passages)
    logger.info("[thread %s] read_chunk(%s) took %.2fs", ctx.deps.thread_id, chunk_id, elapsed)
    return passages[0] if passages else None


@document_agent.tool
def read_surrounding_chunks(
    ctx: RunContext[DocumentAgentDeps], chunk_id: uuid.UUID, window: int = settings.retrieval_neighbor_window
) -> list[SourcePassage]:
    """Read the chunks immediately before/after a given chunk in the same source document."""
    _status(ctx, "read_context", "Reading surrounding context...")
    started = time.perf_counter()
    with ctx.deps.db_lock:
        passages = ctx.deps.retriever.read_surrounding_chunks(
            ctx.deps.db, chunk_id, window=window, allowed_org_ids=ctx.deps.allowed_org_ids
        )
    elapsed = time.perf_counter() - started
    logger.info(
        "[thread %s] read_surrounding_chunks(%s, window=%d) took %.2fs, found %d passage(s)",
        ctx.deps.thread_id,
        chunk_id,
        window,
        elapsed,
        len(passages),
    )
    return _remember(ctx, passages)
