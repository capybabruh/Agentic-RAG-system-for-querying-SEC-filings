from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Organization, OrganizationMember


def get_user_org_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Return the organizations whose documents this user may read."""
    return list(
        db.scalars(select(OrganizationMember.org_id).where(OrganizationMember.user_id == user_id))
    )


def get_org_by_slug(db: Session, slug: str) -> Organization | None:
    return db.scalar(select(Organization).where(Organization.slug == slug))
