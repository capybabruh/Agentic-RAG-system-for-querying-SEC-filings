from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic_ai.models.test import TestModel

from app.assistant.agent import document_agent, read_chunk, read_surrounding_chunks
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.grounding.validator import GroundingError, validate_citations
from app.retrieval.retriever import SourcePassage

ORG_ID = uuid4()


class FakeRetriever:
    def __init__(self, search_result: list[SourcePassage] | None = None):
        self.search_result = search_result or []
        self.search_org_ids: list[list] = []
        self.read_org_ids: list[list] = []

    def search(self, db, query, ticker=None, filing_type=None, *, allowed_org_ids):
        self.search_org_ids.append(allowed_org_ids)
        return self.search_result

    def read_surrounding_chunks(self, db, chunk_id, window=1, *, allowed_org_ids):
        self.read_org_ids.append(allowed_org_ids)
        return []


def make_passage(**overrides) -> SourcePassage:
    defaults = dict(
        chunk_id=uuid4(),
        source_document_id=uuid4(),
        ticker="AAPL",
        filing_type="10-K",
        filing_year="2024",
        page_number=5,
        section_label="Revenue",
        chunk_text="iPhone revenue grew year over year.",
        source_url="https://example.com",
        score=0.1,
    )
    defaults.update(overrides)
    return SourcePassage(**defaults)


@pytest.mark.anyio
async def test_search_filings_tool_call_populates_retrieved_chunk_ids():
    passage = make_passage()
    deps = DocumentAgentDeps(
        user_id="user-1",
        thread_id="thread-1",
        db=None,
        retriever=FakeRetriever([passage]),
        allowed_org_ids=[ORG_ID],
    )

    with document_agent.override(model=TestModel(call_tools=["search_filings"])):
        result = await document_agent.run("What was iPhone revenue?", deps=deps)

    assert passage.chunk_id in deps.retrieved_chunk_ids
    assert isinstance(result.output, GroundedAnswer)


@pytest.mark.anyio
async def test_agent_output_citing_unretrieved_chunk_fails_grounding():
    # Mocking the LLM without also exercising the grounding contract would hide the
    # exact failure mode this system exists to prevent: a confident, uncited-in-fact
    # answer. This asserts validate_citations actually catches it.
    deps = DocumentAgentDeps(
        user_id="user-1",
        thread_id="thread-1",
        db=None,
        retriever=FakeRetriever([]),
        allowed_org_ids=[ORG_ID],
    )
    fabricated_chunk_id = uuid4()

    with document_agent.override(
        model=TestModel(
            call_tools=[],
            custom_output_args={
                "answer": "Revenue grew substantially.",
                "citations": [{"chunk_id": str(fabricated_chunk_id), "quote_text": "Revenue grew."}],
                "has_sufficient_evidence": True,
            },
        )
    ):
        result = await document_agent.run("What was revenue?", deps=deps)

    with pytest.raises(GroundingError):
        validate_citations(result.output, deps.retrieved_chunk_ids)


@pytest.mark.anyio
async def test_search_filings_tool_call_reports_status_when_callback_set():
    passage = make_passage()
    statuses: list[tuple[str, str]] = []
    deps = DocumentAgentDeps(
        user_id="user-1",
        thread_id="thread-1",
        db=None,
        retriever=FakeRetriever([passage]),
        allowed_org_ids=[ORG_ID],
        on_status=lambda stage, message: statuses.append((stage, message)),
    )

    with document_agent.override(model=TestModel(call_tools=["search_filings"])):
        await document_agent.run("What was iPhone revenue?", deps=deps)

    stages = [stage for stage, _ in statuses]
    assert "search" in stages
    assert "search_done" in stages


@pytest.mark.anyio
async def test_search_filings_tool_call_without_callback_does_not_raise():
    passage = make_passage()
    deps = DocumentAgentDeps(
        user_id="user-1",
        thread_id="thread-1",
        db=None,
        retriever=FakeRetriever([passage]),
        allowed_org_ids=[ORG_ID],
    )

    with document_agent.override(model=TestModel(call_tools=["search_filings"])):
        result = await document_agent.run("What was iPhone revenue?", deps=deps)

    assert isinstance(result.output, GroundedAnswer)


@pytest.mark.anyio
async def test_search_filings_tool_scopes_to_the_users_orgs_from_deps():
    retriever = FakeRetriever([make_passage()])
    deps = DocumentAgentDeps(
        user_id="user-1",
        thread_id="thread-1",
        db=None,
        retriever=retriever,
        allowed_org_ids=[ORG_ID],
    )

    with document_agent.override(model=TestModel(call_tools=["search_filings"])):
        await document_agent.run("What was iPhone revenue?", deps=deps)

    assert retriever.search_org_ids == [[ORG_ID]]


@pytest.mark.parametrize("tool", [read_chunk, read_surrounding_chunks])
def test_chunk_reading_tools_scope_to_the_users_orgs_from_deps(tool):
    # Called directly: TestModel can't synthesize a valid UUID for chunk_id.
    retriever = FakeRetriever()
    deps = DocumentAgentDeps(
        user_id="user-1",
        thread_id="thread-1",
        db=None,
        retriever=retriever,
        allowed_org_ids=[ORG_ID],
    )

    tool(SimpleNamespace(deps=deps), uuid4())

    assert retriever.read_org_ids == [[ORG_ID]]


def test_retrieval_tools_expose_no_organization_parameter_to_the_model():
    # The model chooses tool arguments; if any tool accepted an org parameter, a prompt
    # could widen access. Organization scope must only ever come from deps.
    for tool in document_agent._function_toolset.tools.values():
        properties = tool.function_schema.json_schema.get("properties", {})
        assert not any("org" in name for name in properties), (tool.name, properties)


@pytest.fixture
def anyio_backend():
    return "asyncio"
