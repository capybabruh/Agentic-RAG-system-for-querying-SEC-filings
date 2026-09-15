from __future__ import annotations

from supabase import Client, ClientOptions, create_client

from app.config import settings


def get_user_scoped_client(access_token: str) -> Client:
    """Create a Supabase client that executes requests as the authenticated user."""
    token = access_token.strip()
    if not token:
        raise ValueError("access_token cannot be empty")

    options = ClientOptions(headers={"Authorization": f"Bearer {token}"})
    return create_client(settings.supabase_url, settings.supabase_anon_key, options)


def get_service_role_client() -> Client:
    """Create a Supabase client for trusted server-side operations."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
