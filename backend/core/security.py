import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from supabase import Client

from auth.exceptions import AuthenticationError
from core.config import settings


logger = logging.getLogger(__name__)

_SUPPORTED_ALGORITHMS = {"ES256", "RS256", "HS256"}

_JWKS_URL = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

# Module-level singleton so PyJWKClient's built-in JWK Set cache
# (default 300s lifespan) is actually reused across requests instead
# of re-fetching JWKS from Supabase on every call.
_jwks_client = PyJWKClient(_JWKS_URL)


def verify_access_token(token: str) -> dict[str, Any]:
    """
    Verify a Supabase access token and return its verified claims.

    ES256 / RS256 tokens are verified locally against Supabase's JWKS.
    HS256 tokens are verified locally against SUPABASE_JWT_SECRET.
    No live Supabase network call is made for either path.
    """

    if not token:
        raise AuthenticationError("Access token is required.")

    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")

        if not algorithm:
            raise AuthenticationError(
                "Access token does not specify an algorithm."
            )

        if algorithm not in _SUPPORTED_ALGORITHMS:
            raise AuthenticationError(
                "Access token uses an unsupported algorithm."
            )

        if algorithm == "HS256":
            claims = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=settings.jwt_issuer,
                leeway=60,
            )
        else:
            signing_key = _jwks_client.get_signing_key_from_jwt(token)

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=settings.jwt_issuer,
                leeway=60,
            )

    except AuthenticationError:
        raise

    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "Access token has expired."
        ) from exc

    except jwt.InvalidTokenError as exc:
        logger.exception(
            "JWT verification failed: %s: %s",
            type(exc).__name__,
            str(exc),
        )
        raise AuthenticationError(
            "Invalid or expired access token."
        ) from exc

    except Exception as exc:
        logger.exception(
            "Access-token verification failed: %s: %s",
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

    if not claims.get("sub"):
        raise AuthenticationError(
            "Access token does not contain a user ID."
        )

    return dict(claims)