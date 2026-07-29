from supabase import Client, create_client

from core.config import settings


def create_supabase_client() -> Client:
    """Create the Supabase client used by the backend."""

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )


supabase: Client = create_supabase_client()


def get_supabase_client() -> Client:
    """Return the shared Supabase client."""

    return supabase