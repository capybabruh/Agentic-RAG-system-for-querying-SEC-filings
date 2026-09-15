"""Change document chunk embeddings to Mistral Embed dimensions.

Revision ID: 20260904_000002
Revises: 20260901_000001
"""
from __future__ import annotations

from alembic import op

revision = "20260904_000002"
down_revision = "20260901_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM document_chunks) THEN
                RAISE EXCEPTION
                    'document_chunks must be empty before changing embedding dimensions';
            END IF;
        END $$
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM document_chunks) THEN
                RAISE EXCEPTION
                    'document_chunks must be empty before reverting embedding dimensions';
            END IF;
        END $$
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
