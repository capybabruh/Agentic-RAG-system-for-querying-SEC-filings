from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from supabase_auth.types import UserResponse

from app.database.models import User


def get_or_create_user(db: Session, auth_user: UserResponse) -> User:
    """Resolve the authenticated Supabase user to the local application user."""
    supabase_user = auth_user.user
    user_id = uuid.UUID(supabase_user.id)
    user = db.scalar(select(User).where(User.id == user_id))

    if user is None:
        user = User(id=user_id, email=supabase_user.email or "")
        db.add(user)
        db.flush()
    elif supabase_user.email and user.email != supabase_user.email:
        user.email = supabase_user.email

    return user
