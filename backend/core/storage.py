from supabase import Client, create_client

from core.config import settings

REQUIREMENT_SOURCES_BUCKET = "requirement-sources"
REPORTS_BUCKET = "reports"


def create_storage_client() -> Client:
    """
    Service-role Supabase client used ONLY for storage.objects access on
    private buckets (e.g. `requirement-sources`), which have no RLS
    policies of their own — see 10_storage.sql. This client must never be
    imported by API route modules directly, and SUPABASE_SERVICE_ROLE_KEY
    must never be sent to the frontend.
    """

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )


_storage_client: Client = create_storage_client()


def get_storage_client() -> Client:
    """Return the shared service-role storage client."""

    return _storage_client