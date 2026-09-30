"""Supabase client connection using service role key."""

from __future__ import annotations

from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions
from ..config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

_client: Client | None = None


def get_supabase() -> Client:
    """Get or create the Supabase client singleton."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
            )
        _client = create_client(
            SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
            options=SyncClientOptions(
                postgrest_client_timeout=5.0,
                auto_refresh_token=False,
                persist_session=False,
            ),
        )
    return _client
