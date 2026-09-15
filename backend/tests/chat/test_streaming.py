from __future__ import annotations

import json
import uuid

from app.chat.schemas import CitationResponse
from app.chat.streaming import (
    format_citations,
    format_done,
    format_error,
    format_status,
    format_text_delta,
    format_thread_title,
)


def parse_event(raw: str) -> tuple[str, dict]:
    lines = raw.strip("\n").split("\n")
    event = lines[0].removeprefix("event: ")
    data = json.loads(lines[1].removeprefix("data: "))
    return event, data


def test_format_text_delta_carries_the_given_text_verbatim():
    event, data = parse_event(format_text_delta("hello "))

    assert event == "text_delta"
    assert data == {"text": "hello "}


def test_format_citations_serializes_each_citation_with_document_metadata():
    citation_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    citations = [
        CitationResponse(
            id=citation_id,
            chunk_id=chunk_id,
            quote_text="Revenue grew.",
            page_number=None,
            section_label="Revenue",
            ticker="AAPL",
            filing_type="10-K",
            filing_date=None,
            document_title="Apple 10-K",
            source_url="https://example.com/aapl.htm",
        ),
    ]

    event, data = parse_event(format_citations(citations))

    assert event == "citations"
    assert data["citations"] == [
        {
            "id": str(citation_id),
            "chunk_id": str(chunk_id),
            "quote_text": "Revenue grew.",
            "page_number": None,
            "section_label": "Revenue",
            "ticker": "AAPL",
            "filing_type": "10-K",
            "filing_date": None,
            "document_title": "Apple 10-K",
            "source_url": "https://example.com/aapl.htm",
        }
    ]


def test_format_citations_empty_list_is_empty_array():
    event, data = parse_event(format_citations([]))

    assert event == "citations"
    assert data == {"citations": []}


def test_format_status_carries_stage_and_message():
    event, data = parse_event(format_status("search", "Searching filings..."))

    assert event == "status"
    assert data == {"stage": "search", "message": "Searching filings..."}


def test_format_error_carries_the_message():
    event, data = parse_event(format_error("The answer could not be grounded."))

    assert event == "error"
    assert data == {"message": "The answer could not be grounded."}


def test_format_done_has_no_payload():
    assert format_done() == "event: done\ndata: {}\n\n"


def test_format_thread_title_carries_the_title():
    event, data = parse_event(format_thread_title("Apple's Q4 revenue"))

    assert event == "thread_title"
    assert data == {"title": "Apple's Q4 revenue"}
