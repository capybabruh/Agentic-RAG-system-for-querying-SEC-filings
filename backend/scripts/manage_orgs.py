"""Admin CLI for organizations and their members.

Members are looked up by email in the local users table, so a user must have
signed in to the app at least once before they can be added to an organization.

Run from backend/ with:
    uv run python scripts/manage_orgs.py create-org amazon "Amazon"
    uv run python scripts/manage_orgs.py add-member an@amazon.com amazon
    uv run python scripts/manage_orgs.py remove-member an@amazon.com amazon
    uv run python scripts/manage_orgs.py list
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Organization, OrganizationMember, SourceDocument, User
from app.database.organizations import get_org_by_slug
from app.database.session import SessionLocal


class AdminError(Exception):
    """Raised for invalid admin input; printed without a traceback."""


def create_org(db: Session, slug: str, name: str) -> Organization:
    slug = slug.strip().lower()
    if not slug:
        raise AdminError("Organization slug cannot be empty")
    if get_org_by_slug(db, slug) is not None:
        raise AdminError(f"Organization '{slug}' already exists")
    org = Organization(slug=slug, name=name.strip() or slug)
    db.add(org)
    db.flush()
    return org


def _require_org(db: Session, slug: str) -> Organization:
    org = get_org_by_slug(db, slug.strip().lower())
    if org is None:
        raise AdminError(f"Organization '{slug}' does not exist — create it with create-org first")
    return org


def _require_user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user is None:
        raise AdminError(
            f"No user with email '{email}' — they must sign in to the app once before being added"
        )
    return user


def add_member(db: Session, email: str, slug: str, role: str = "member") -> OrganizationMember:
    org = _require_org(db, slug)
    user = _require_user(db, email)
    existing = db.get(OrganizationMember, (org.id, user.id))
    if existing is not None:
        raise AdminError(f"'{email}' is already a member of '{org.slug}'")
    member = OrganizationMember(org_id=org.id, user_id=user.id, role=role)
    db.add(member)
    db.flush()
    return member


def remove_member(db: Session, email: str, slug: str) -> None:
    org = _require_org(db, slug)
    user = _require_user(db, email)
    member = db.get(OrganizationMember, (org.id, user.id))
    if member is None:
        raise AdminError(f"'{email}' is not a member of '{org.slug}'")
    db.delete(member)
    db.flush()


def list_orgs(db: Session) -> None:
    orgs = db.scalars(select(Organization).order_by(Organization.slug)).all()
    if not orgs:
        print("No organizations yet.")
    for org in orgs:
        document_count = db.scalar(
            select(func.count()).select_from(SourceDocument).where(SourceDocument.org_id == org.id)
        )
        emails = db.scalars(
            select(User.email)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.org_id == org.id)
            .order_by(User.email)
        ).all()
        print(f"{org.slug} ({org.name}) — {document_count} document(s)")
        for email in emails:
            print(f"  - {email}")

    unassigned = db.scalar(
        select(func.count()).select_from(SourceDocument).where(SourceDocument.org_id.is_(None))
    )
    if unassigned:
        print(f"\n{unassigned} document(s) have no organization and are visible to nobody.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-org", help="Create an organization")
    create.add_argument("slug", help="Short unique id, e.g. amazon")
    create.add_argument("name", help="Display name, e.g. Amazon")

    add = commands.add_parser("add-member", help="Give a user access to an organization's documents")
    add.add_argument("email")
    add.add_argument("slug")
    add.add_argument("--role", default="member")

    remove = commands.add_parser("remove-member", help="Revoke a user's access to an organization")
    remove.add_argument("email")
    remove.add_argument("slug")

    commands.add_parser("list", help="List organizations, members and document counts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        with SessionLocal.begin() as db:
            if args.command == "create-org":
                org = create_org(db, args.slug, args.name)
                print(f"Created organization '{org.slug}'")
            elif args.command == "add-member":
                add_member(db, args.email, args.slug, args.role)
                print(f"Added '{args.email}' to '{args.slug}'")
            elif args.command == "remove-member":
                remove_member(db, args.email, args.slug)
                print(f"Removed '{args.email}' from '{args.slug}'")
            else:
                list_orgs(db)
    except AdminError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
