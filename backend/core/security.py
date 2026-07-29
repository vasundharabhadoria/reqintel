import logging
from typing import Any

from supabase import Client

from auth.exceptions import AuthenticationError


logger = logging.getLogger(__name__)


def verify_access_token(
    supabase: Client,
    token: str,
) -> dict[str, Any]:
    """
    Verify a Supabase access token and return its verified claims.

    Supabase Auth verifies asymmetric JWTs such as ES256 tokens
    against the project's JWKS endpoint.
    """

    if not token:
        raise AuthenticationError(
            "Access token is required."
        )

    try:
        response = supabase.auth.get_claims(token)

        if response is None:
            raise AuthenticationError(
                "Invalid or expired access token."
            )

        claims = response["claims"]

    except AuthenticationError:
        raise

    except Exception as exc:
        logger.exception(
            "Supabase access-token verification failed: %s: %s",
            type(exc).__name__,
            str(exc),
        )

        raise AuthenticationError(
            "Invalid or expired access token."
        ) from exc

    if not claims:
        raise AuthenticationError(
            "Access token contains no claims."
        )

    user_id = claims.get("sub")

    if not user_id:
        raise AuthenticationError(
            "Access token does not contain a user ID."
        )

    return dict(claims)