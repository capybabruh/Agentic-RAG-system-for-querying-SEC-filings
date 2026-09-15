"""Query-to-source-passage retrieval: embed, run hybrid search, fuse, hydrate rows."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from mistralai.client import Mistral
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keywords import extract_keywords
from app.retrieval.queries import fulltext_search, vector_search


@dataclass
class SourcePassage:
    chunk_id: uuid.UUID
    source_document_id: uuid.UUID
    ticker: str | None
    filing_type: str | None
    filing_year: str | None
    page_number: int | None
    section_label: str | None
    chunk_text: str
    source_url: str | None
    score: float


def _passage_from_rows(chunk: DocumentChunk, document: SourceDocument, score: float) -> SourcePassage:
    filing_year = str(document.filing_date.year) if document.filing_date else None
    return SourcePassage(
        chunk_id=chunk.id,
        source_document_id=document.id,
        ticker=document.company_ticker,
        filing_type=document.filing_type,
        filing_year=filing_year,
        page_number=chunk.page_number,
        section_label=chunk.section_label,
        chunk_text=chunk.chunk_text,
        source_url=document.source_url,
        score=score,
    )


class DocumentRetriever:
    def __init__(
        self,
        mistral_client: Mistral,
        embedding_model: str,
        chat_model: str = settings.mistral_chat_model,
        keyword_extraction_enabled: bool = settings.retrieval_keyword_extraction_enabled,
    ) -> None:
        self._client = mistral_client
        self._embedding_model = embedding_model
        self._chat_model = chat_model
        self._keyword_extraction_enabled = keyword_extraction_enabled

    def _embed_query(self, query: str) -> list[float]:
        response = self._client.embeddings.create(
            model=self._embedding_model,
            inputs=[query],
            timeout_ms=settings.mistral_request_timeout_ms,
        )
        return response.data[0].embedding

    def _fulltext_query(self, query: str) -> str:
        if not self._keyword_extraction_enabled:
            return query
        return extract_keywords(self._client, self._chat_model, query)

    def _load_passages(
        self, db: Session, ordered_scores: list[tuple[uuid.UUID, float]]
    ) -> list[SourcePassage]:
        if not ordered_scores:
            return []
        chunk_ids = [chunk_id for chunk_id, _ in ordered_scores]
        rows = db.execute(
            select(DocumentChunk, SourceDocument)
            .join(SourceDocument, DocumentChunk.source_document_id == SourceDocument.id)
            .where(DocumentChunk.id.in_(chunk_ids))
        ).all()
        rows_by_id = {chunk.id: (chunk, document) for chunk, document in rows}
        passages = []
        for chunk_id, score in ordered_scores:
            row = rows_by_id.get(chunk_id)
            if row is None:
                continue
            chunk, document = row
            passages.append(_passage_from_rows(chunk, document, score))
        return passages

    def search(
        self,
        db: Session,
        query: str,
        top_k: int = settings.retrieval_top_k,
        candidate_k: int = settings.retrieval_candidate_k,
        ticker: str | None = None,
        filing_type: str | None = None,
    ) -> list[SourcePassage]:
        # _embed_query and _fulltext_query are both independent Mistral network calls on the
        # same raw query — run them concurrently rather than paying their durations serially.
        with ThreadPoolExecutor(max_workers=2) as executor:
            embedding_future = executor.submit(self._embed_query, query)
            fulltext_future = executor.submit(self._fulltext_query, query)
            query_embedding = embedding_future.result()
            fulltext_query = fulltext_future.result()

        vector_results = vector_search(db, query_embedding, candidate_k, ticker, filing_type)
        text_results = fulltext_search(db, fulltext_query, candidate_k, ticker, filing_type)

        fused = reciprocal_rank_fusion(
            [
                [result.chunk_id for result in vector_results],
                [result.chunk_id for result in text_results],
            ]
        )[:top_k]
        return self._load_passages(db, fused)

    def read_surrounding_chunks(
        self, db: Session, chunk_id: uuid.UUID, window: int = settings.retrieval_neighbor_window
    ) -> list[SourcePassage]:
        target = db.get(DocumentChunk, chunk_id)
        if target is None:
            return []

        rows = db.execute(
            select(DocumentChunk, SourceDocument)
            .join(SourceDocument, DocumentChunk.source_document_id == SourceDocument.id)
            .where(
                DocumentChunk.source_document_id == target.source_document_id,
                DocumentChunk.chunk_index >= target.chunk_index - window,
                DocumentChunk.chunk_index <= target.chunk_index + window,
            )
            .order_by(DocumentChunk.chunk_index)
        ).all()
        return [_passage_from_rows(chunk, document, score=0.0) for chunk, document in rows]
