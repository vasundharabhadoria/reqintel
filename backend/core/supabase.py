from functools import lru_cache

from postgrest import SyncPostgrestClient
from supabase import Client, ClientOptions, create_client

from core.config import settings

_REST_URL = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def create_auth_client() -> Client:
    """
    Return a NEW, stateless Supabase client for one Auth operation.

    supabase-py reacts to SIGNED_IN / TOKEN_REFRESHED / SIGNED_OUT by
    rewriting the client's Authorization header and keeping the session in
    memory. On a client shared by every request that leaks one user's token
    into another user's calls. Every sign-up, sign-in, refresh, recovery and
    sign-out therefore uses its own throw-away client, and no client that is
    shared between requests is ever signed in.
    """

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
        options=ClientOptions(
            persist_session=False,
            auto_refresh_token=False,
        ),
    )


def create_admin_client() -> Client:
    """
    Return a NEW, stateless service-role client for the Supabase Auth Admin API.

    Used ONLY by account deletion (auth.admin.delete_user), which cannot be
    done with a user token. It is created per call, never shared and never
    signed in, and must never be imported by API route modules or exposed
    to the frontend. SUPABASE_SERVICE_ROLE_KEY stays on the server.
    """

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
        options=ClientOptions(
            persist_session=False,
            auto_refresh_token=False,
        ),
    )


@lru_cache
def get_rules_client() -> SyncPostgrestClient:
    """
    Read-only client for the global Master Module rule configuration
    (master_rules / rule_categories).

    That data is shared configuration, not per-user data, so it is read with
    the service-role key. The headers are fixed at creation and never
    modified, so no user's token can ever end up on this client. Use it only
    for those two tables. Per-user and admin writes must use the per-request
    client from core.dependencies.get_user_db instead.
    """

    return SyncPostgrestClient(
        _REST_URL,
        headers={
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=10,
    )
