from __future__ import annotations

from types import SimpleNamespace

from app.config import settings
from app.retrieval.keywords import extract_keywords


class FakeChat:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


class FakeClient:
    def __init__(self, chat: FakeChat):
        self.chat = chat


def test_extract_keywords_parses_comma_separated_terms():
    client = FakeClient(FakeChat(content="revenue mix, iPhone, Services, Mac"))

    result = extract_keywords(client, "mistral-small-latest", "how did revenue mix change?")

    assert result == "revenue mix iPhone Services Mac"
    assert client.chat.calls[0]["model"] == "mistral-small-latest"
    assert client.chat.calls[0]["timeout_ms"] == settings.retrieval_keyword_extraction_timeout_ms


def test_extract_keywords_trims_whitespace_and_drops_empty_terms():
    client = FakeClient(FakeChat(content=" revenue mix ,, iPhone ,  "))

    result = extract_keywords(client, "mistral-small-latest", "question")

    assert result == "revenue mix iPhone"


def test_extract_keywords_falls_back_to_raw_query_on_empty_content():
    client = FakeClient(FakeChat(content="   "))

    result = extract_keywords(client, "mistral-small-latest", "original question")

    assert result == "original question"


def test_extract_keywords_falls_back_to_raw_query_on_error():
    client = FakeClient(FakeChat(error=RuntimeError("rate limited")))

    result = extract_keywords(client, "mistral-small-latest", "original question")

    assert result == "original question"
