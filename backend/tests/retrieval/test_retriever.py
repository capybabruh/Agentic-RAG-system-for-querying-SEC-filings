from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import app.retrieval.retriever as retriever_module
from app.database.models import DocumentChunk, SourceDocument
from app.retrieval.queries import RankedChunkId
from app.retrieval.retriever import DocumentRetriever


class FakeEmbeddingsClient:
    def __init__(self, vector):
        self.vector = vector
        self.calls = []

    def create(self, model, inputs, **kwargs):
        self.calls.append((model, inputs))
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.vector)])


class FakeChatClient:
    def __init__(self, content="keyword one, keyword two"):
        self.content = content
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


class FakeMistralClient:
    def __init__(self, vector, chat_content="keyword one, keyword two"):
        self.embeddings = FakeEmbeddingsClient(vector)
        self.chat = FakeChatClient(chat_content)


def make_document(ticker="AAPL", filing_type="10-K", source_url="https://example/aapl.htm"):
    return SourceDocument(
        id=uuid.uuid4(),
        title="AAPL 10-K",
        company_ticker=ticker,
        filing_type=filing_type,
        filing_date=datetime(2024, 11, 1, tzinfo=UTC),
        source_url=source_url,
        content_markdown="...",
    )


def make_chunk(document, chunk_index, page_number=None, section_label=None, text="chunk text"):
    return DocumentChunk(
        id=uuid.uuid4(),
        source_document_id=document.id,
        chunk_index=chunk_index,
        page_number=page_number,
        section_label=section_label,
        chunk_text=text,
    )


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, chunks_by_id=None, execute_rows=None):
        self._chunks_by_id = chunks_by_id or {}
        self._execute_rows = execute_rows or []

    def get(self, model, id):
        return self._chunks_by_id.get(id)

    def execute(self, stmt):
        return FakeResult(self._execute_rows)


def test_search_fuses_vector_and_fulltext_and_hydrates_in_fused_order(monkeypatch):
    document = make_document()
    chunk_a = make_chunk(document, 0, page_number=5, section_label="Revenue")
    chunk_b = make_chunk(document, 1, page_number=6, section_label="Segments")

    monkeypatch.setattr(
        retriever_module,
        "vector_search",
        lambda db, embedding, limit, ticker, filing_type: [
            RankedChunkId(chunk_id=chunk_a.id, rank=0, score=0.1),
            RankedChunkId(chunk_id=chunk_b.id, rank=1, score=0.2),
        ],
    )
    monkeypatch.setattr(
        retriever_module,
        "fulltext_search",
        lambda db, query, limit, ticker, filing_type: [
            RankedChunkId(chunk_id=chunk_b.id, rank=0, score=1.5),
        ],
    )

    session = FakeSession(execute_rows=[(chunk_a, document), (chunk_b, document)])
    client = FakeMistralClient(vector=[0.1, 0.2, 0.3])
    retriever = DocumentRetriever(client, "mistral-embed")

    passages = retriever.search(session, "revenue mix", top_k=2, candidate_k=10)

    assert [p.chunk_id for p in passages] == [chunk_b.id, chunk_a.id]
    assert client.embeddings.calls == [("mistral-embed", ["revenue mix"])]
    assert passages[0].section_label == "Segments"
    assert passages[0].ticker == "AAPL"
    assert passages[0].filing_year == "2024"


def test_search_respects_top_k_after_fusion(monkeypatch):
    document = make_document()
    chunks = [make_chunk(document, i) for i in range(3)]

    monkeypatch.setattr(
        retriever_module,
        "vector_search",
        lambda db, embedding, limit, ticker, filing_type: [
            RankedChunkId(chunk_id=c.id, rank=i, score=0.0) for i, c in enumerate(chunks)
        ],
    )
    monkeypatch.setattr(
        retriever_module, "fulltext_search", lambda db, query, limit, ticker, filing_type: []
    )

    session = FakeSession(execute_rows=[(c, document) for c in chunks[:2]])
    client = FakeMistralClient(vector=[0.0])
    retriever = DocumentRetriever(client, "mistral-embed")

    passages = retriever.search(session, "query", top_k=2, candidate_k=10)

    assert [p.chunk_id for p in passages] == [chunks[0].id, chunks[1].id]


def test_search_with_no_results_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        retriever_module, "vector_search", lambda db, embedding, limit, ticker, filing_type: []
    )
    monkeypatch.setattr(
        retriever_module, "fulltext_search", lambda db, query, limit, ticker, filing_type: []
    )

    session = FakeSession()
    client = FakeMistralClient(vector=[0.0])
    retriever = DocumentRetriever(client, "mistral-embed")

    assert retriever.search(session, "nothing matches") == []


def test_read_surrounding_chunks_returns_neighbors_ordered_by_index():
    document = make_document()
    target = make_chunk(document, 5)
    neighbors = [make_chunk(document, i) for i in (4, 5, 6)]

    session = FakeSession(
        chunks_by_id={target.id: target},
        execute_rows=[(c, document) for c in neighbors],
    )
    retriever = DocumentRetriever(FakeMistralClient([]), "mistral-embed")

    passages = retriever.read_surrounding_chunks(session, target.id, window=1)

    assert [p.chunk_id for p in passages] == [c.id for c in neighbors]


def test_read_surrounding_chunks_missing_target_returns_empty():
    session = FakeSession()
    retriever = DocumentRetriever(FakeMistralClient([]), "mistral-embed")

    assert retriever.read_surrounding_chunks(session, uuid.uuid4()) == []


def test_search_sends_extracted_keywords_to_fulltext_search(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        retriever_module, "vector_search", lambda db, embedding, limit, ticker, filing_type: []
    )

    def fake_fulltext_search(db, query, limit, ticker, filing_type):
        captured["query"] = query
        return []

    monkeypatch.setattr(retriever_module, "fulltext_search", fake_fulltext_search)

    client = FakeMistralClient(vector=[0.0], chat_content="revenue mix, iPhone, Services")
    retriever = DocumentRetriever(client, "mistral-embed", chat_model="mistral-small-latest")

    retriever.search(FakeSession(), "how did revenue mix change across products?")

    assert captured["query"] == "revenue mix iPhone Services"
    assert client.chat.calls[0]["model"] == "mistral-small-latest"


def test_search_uses_raw_query_when_keyword_extraction_disabled(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        retriever_module, "vector_search", lambda db, embedding, limit, ticker, filing_type: []
    )

    def fake_fulltext_search(db, query, limit, ticker, filing_type):
        captured["query"] = query
        return []

    monkeypatch.setattr(retriever_module, "fulltext_search", fake_fulltext_search)

    client = FakeMistralClient(vector=[0.0])
    retriever = DocumentRetriever(client, "mistral-embed", keyword_extraction_enabled=False)

    retriever.search(FakeSession(), "how did revenue mix change across products?")

    assert captured["query"] == "how did revenue mix change across products?"
    assert client.chat.calls == []
