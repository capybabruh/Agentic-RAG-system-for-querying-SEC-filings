from __future__ import annotations

import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import manage_orgs  # noqa: E402

from app.database.base import Base
from app.database.models import Organization, OrganizationMember, User
from app.database.organizations import get_user_org_ids


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Organization.__table__, OrganizationMember.__table__],
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def make_user(db: Session, email: str) -> User:
    user = User(id=uuid.uuid4(), email=email)
    db.add(user)
    db.flush()
    return user


def test_create_org_normalizes_slug(session):
    org = manage_orgs.create_org(session, "  Amazon ", "Amazon")

    assert org.slug == "amazon"


def test_create_org_rejects_duplicate_slug(session):
    manage_orgs.create_org(session, "amazon", "Amazon")

    with pytest.raises(manage_orgs.AdminError, match="already exists"):
        manage_orgs.create_org(session, "amazon", "Amazon again")


def test_add_member_grants_access_to_that_org_only(session):
    amazon = manage_orgs.create_org(session, "amazon", "Amazon")
    manage_orgs.create_org(session, "meta", "Meta")
    an = make_user(session, "an@amazon.com")

    manage_orgs.add_member(session, "AN@amazon.com", "amazon")

    assert get_user_org_ids(session, an.id) == [amazon.id]


def test_add_member_requires_existing_org_and_user(session):
    manage_orgs.create_org(session, "amazon", "Amazon")
    make_user(session, "an@amazon.com")

    with pytest.raises(manage_orgs.AdminError, match="does not exist"):
        manage_orgs.add_member(session, "an@amazon.com", "meta")
    with pytest.raises(manage_orgs.AdminError, match="must sign in"):
        manage_orgs.add_member(session, "nobody@amazon.com", "amazon")


def test_add_member_rejects_duplicate_membership(session):
    manage_orgs.create_org(session, "amazon", "Amazon")
    make_user(session, "an@amazon.com")
    manage_orgs.add_member(session, "an@amazon.com", "amazon")

    with pytest.raises(manage_orgs.AdminError, match="already a member"):
        manage_orgs.add_member(session, "an@amazon.com", "amazon")


def test_remove_member_revokes_access(session):
    manage_orgs.create_org(session, "amazon", "Amazon")
    an = make_user(session, "an@amazon.com")
    manage_orgs.add_member(session, "an@amazon.com", "amazon")

    manage_orgs.remove_member(session, "an@amazon.com", "amazon")

    assert get_user_org_ids(session, an.id) == []


def test_user_with_no_membership_has_no_orgs(session):
    manage_orgs.create_org(session, "amazon", "Amazon")
    binh = make_user(session, "binh@meta.com")

    assert get_user_org_ids(session, binh.id) == []
