"""Add organizations and scope source documents to an organization.

Documents with a NULL org_id are visible to nobody: retrieval only returns
documents whose org_id is one of the requesting user's organizations. Existing
rows are backfilled by re-running data/ingest_documents.py with --org.

Revision ID: 20261028_000003
Revises: 20260904_000002
"""
from __future__ import annotations

from alembic import op

revision = "20261028_000003"
down_revision = "20260904_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE organizations (
            id UUID PRIMARY KEY,
            slug VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE organization_members (
            org_id UUID NOT NULL,
            user_id UUID NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'member',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (org_id, user_id),
            CONSTRAINT fk_organization_members_org
                FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
            CONSTRAINT fk_organization_members_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX idx_organization_members_user_id ON organization_members (user_id)")

    op.execute("ALTER TABLE source_documents ADD COLUMN org_id UUID")
    op.execute(
        """
        ALTER TABLE source_documents
            ADD CONSTRAINT fk_source_documents_org
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        """
    )
    op.execute("CREATE INDEX idx_source_documents_org_id ON source_documents (org_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_source_documents_org_id")
    op.execute("ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS fk_source_documents_org")
    op.execute("ALTER TABLE source_documents DROP COLUMN IF EXISTS org_id")
    op.execute("DROP TABLE IF EXISTS organization_members")
    op.execute("DROP TABLE IF EXISTS organizations")
