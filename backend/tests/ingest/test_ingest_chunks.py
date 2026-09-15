from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
sys.path.insert(0, str(DATA_DIR))

import ingest_chunks  # noqa: E402


def make_chunk(doc_items=None, headings=None, text="Example passage."):
    return SimpleNamespace(
        text=text,
        meta=SimpleNamespace(doc_items=doc_items or [], headings=headings),
    )


def make_filing(**overrides):
    filing = {
        "ticker": "AAPL",
        "form": "10-K",
        "report_date": "2024-09-28",
        "filing_date": "2024-11-01",
        "accession_number": "0000320193-24-000123",
        "source_url": "https://www.sec.gov/example",
    }
    filing.update(overrides)
    return filing


def test_chunk_page_number_takes_earliest_page_across_doc_items():
    raw_meta = {
        "doc_items": [
            {"prov": [{"page_no": 12}]},
            {"prov": [{"page_no": 10}, {"page_no": 14}]},
        ]
    }
    assert ingest_chunks.chunk_page_number(raw_meta) == 10


def test_chunk_page_number_missing_returns_none():
    assert ingest_chunks.chunk_page_number({}) is None
    assert ingest_chunks.chunk_page_number({"doc_items": []}) is None


def test_chunk_section_label_uses_deepest_heading():
    raw_meta = {"headings": ["Item 7. MD&A", "Revenue by Segment"]}
    assert ingest_chunks.chunk_section_label(raw_meta) == "Revenue by Segment"


def test_chunk_section_label_missing_returns_none():
    assert ingest_chunks.chunk_section_label({}) is None
    assert ingest_chunks.chunk_section_label({"headings": []}) is None


def test_chunk_metadata_extracts_page_and_section_from_doc_items():
    chunk = make_chunk(
        doc_items=[{"prov": [{"page_no": 42}]}],
        headings=["Item 7. MD&A", "Revenue by Segment"],
    )
    metadata = ingest_chunks.chunk_metadata(chunk, make_filing(), "hybrid", "mistral-embed")

    assert metadata["ticker"] == "AAPL"
    assert metadata["filing_type"] == "10-K"
    assert metadata["filing_year"] == "2024"
    assert metadata["page_number"] == 42
    assert metadata["section_label"] == "Revenue by Segment"


def test_chunk_metadata_omits_page_and_section_when_absent():
    chunk = make_chunk(doc_items=[], headings=None)
    metadata = ingest_chunks.chunk_metadata(chunk, make_filing(), "hybrid", "mistral-embed")

    assert "page_number" not in metadata
    assert "section_label" not in metadata


def test_chunk_text_uses_contextualized_text_for_token_count():
    class FakeTokenizer:
        def count_tokens(self, text: str) -> int:
            return len(text.split())

    class FakeChunker:
        tokenizer = FakeTokenizer()

        def contextualize(self, chunk):
            return f"{chunk.meta.headings[-1]}\n{chunk.text}"

    chunk = make_chunk(headings=["Item 7"], text="Revenue grew year over year.")
    plain_text, embedding_text, token_count = ingest_chunks.chunk_text(FakeChunker(), chunk)

    assert plain_text == "Revenue grew year over year."
    assert embedding_text == "Item 7\nRevenue grew year over year."
    assert token_count == len(embedding_text.split())


def test_chunk_text_rejects_empty_chunk():
    chunk = make_chunk(text="   ")
    with pytest.raises(ValueError):
        ingest_chunks.chunk_text(SimpleNamespace(), chunk)


def test_embedding_batches_splits_by_batch_size_and_preserves_order(monkeypatch):
    class FakeResponse:
        def __init__(self, data):
            self.data = data

    class FakeEmbeddingItem:
        def __init__(self, index, embedding):
            self.index = index
            self.embedding = embedding

    class FakeEmbeddingsClient:
        def __init__(self, dimensions):
            self.dimensions = dimensions
            self.calls: list[list[str]] = []

        def create(self, model, inputs):
            self.calls.append(list(inputs))
            # Return out of order to prove the sort-by-index reordering works.
            items = [FakeEmbeddingItem(i, [float(i)] * self.dimensions) for i in range(len(inputs))]
            return FakeResponse(list(reversed(items)))

    class FakeClient:
        def __init__(self, dimensions):
            self.embeddings = FakeEmbeddingsClient(dimensions)

    monkeypatch.setattr(ingest_chunks.settings, "mistral_embedding_dimensions", 3)
    client = FakeClient(dimensions=3)
    texts = [f"chunk-{i}" for i in range(5)]

    batches = list(ingest_chunks.embedding_batches(client, texts, batch_size=2))

    assert len(client.embeddings.calls) == 3
    assert client.embeddings.calls[0] == ["chunk-0", "chunk-1"]
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert batches[0][0] == [0.0, 0.0, 0.0]
    assert batches[0][1] == [1.0, 1.0, 1.0]


def test_embedding_batches_raises_on_dimension_mismatch(monkeypatch):
    class FakeResponse:
        def __init__(self, data):
            self.data = data

    class FakeEmbeddingItem:
        def __init__(self, index, embedding):
            self.index = index
            self.embedding = embedding

    class FakeEmbeddingsClient:
        def create(self, model, inputs):
            return FakeResponse([FakeEmbeddingItem(0, [0.1, 0.2])])

    class FakeClient:
        embeddings = FakeEmbeddingsClient()

    monkeypatch.setattr(ingest_chunks.settings, "mistral_embedding_dimensions", 1024)
    with pytest.raises(ValueError, match="dimension mismatch"):
        list(ingest_chunks.embedding_batches(FakeClient(), ["only chunk"], batch_size=10))
