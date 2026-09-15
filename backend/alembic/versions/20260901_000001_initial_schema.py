"""Initial database schema for document chat and retrieval.

Revision ID: 20260901_000001
Revises: 
Create Date: 2026-09-01 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260901_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            full_name VARCHAR(255),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE source_documents (
            id UUID PRIMARY KEY,
            user_id UUID,
            title VARCHAR(255) NOT NULL,
            company_ticker VARCHAR(32),
            filing_type VARCHAR(64),
            filing_date TIMESTAMPTZ,
            source_url VARCHAR(2048),
            content_markdown TEXT NOT NULL,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_source_documents_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE document_chunks (
            id UUID PRIMARY KEY,
            source_document_id UUID NOT NULL,
            chunk_index INTEGER NOT NULL,
            page_number INTEGER,
            section_label VARCHAR(255),
            chunk_text TEXT NOT NULL,
            token_count INTEGER,
            embedding vector(1536) NOT NULL,
            search_vector TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(chunk_text, ''))
            ) STORED,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_document_chunks_source_document
                FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE chat_threads (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL,
            title VARCHAR(255),
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_chat_threads_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE chat_messages (
            id UUID PRIMARY KEY,
            thread_id UUID NOT NULL,
            sender VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            message_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_chat_messages_thread
                FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE message_citations (
            id UUID PRIMARY KEY,
            message_id UUID NOT NULL,
            chunk_id UUID,
            quote_text TEXT NOT NULL,
            page_number INTEGER,
            section_label VARCHAR(255),
            start_char INTEGER,
            end_char INTEGER,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_message_citations_message
                FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
            CONSTRAINT fk_message_citations_chunk
                FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE SET NULL
        )
        """
    )

    op.execute("CREATE INDEX idx_source_documents_user_id ON source_documents (user_id)")
    op.execute("CREATE INDEX idx_source_documents_company_ticker ON source_documents (company_ticker)")
    op.execute("CREATE INDEX idx_source_documents_filing_type ON source_documents (filing_type)")
    op.execute("CREATE INDEX idx_chat_threads_user_id ON chat_threads (user_id)")
    op.execute("CREATE INDEX idx_chat_messages_thread_id ON chat_messages (thread_id)")
    op.execute("CREATE INDEX idx_message_citations_message_id ON message_citations (message_id)")
    op.execute("CREATE INDEX idx_message_citations_chunk_id ON message_citations (chunk_id)")
    op.execute("CREATE INDEX ix_document_chunks_document_order ON document_chunks (source_document_id, chunk_index)")
    op.execute("CREATE INDEX ix_document_chunks_search_vector ON document_chunks USING GIN (search_vector)")
    op.execute("CREATE INDEX ix_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS message_citations")
    op.execute("DROP TABLE IF EXISTS chat_messages")
    op.execute("DROP TABLE IF EXISTS chat_threads")
    op.execute("DROP TABLE IF EXISTS document_chunks")
    op.execute("DROP TABLE IF EXISTS source_documents")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP EXTENSION IF EXISTS vector")
