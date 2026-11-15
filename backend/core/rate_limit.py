"""
Small in-memory sliding-window rate limiter for the auth endpoints.

Limits are per process. Behind several workers or containers each process
counts separately, so treat this as a first line of defence in addition to
Supabase's own server-side Auth rate limits, not a replacement for a shared
limiter (e.g. at the reverse proxy) in production.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from core.config import settings

_MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """Allow at most `limit` hits per `window_seconds` for each key."""

    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def hit(self, key: str) -> None:
        """Record a hit; raise 429 when the key is over its limit."""

        now = time.monotonic()
        cutoff = now - self.window

        with self._lock:
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._prune(cutoff)

            hits = self._hits[key]

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                retry_after = max(1, int(hits[0] + self.window - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait and try again.",
                    headers={"Retry-After": str(retry_after)},
                )

            hits.append(now)

    def _prune(self, cutoff: float) -> None:
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]


def client_ip(request: Request) -> str:
    """Best-effort client address for rate limiting."""

    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first

    return request.client.host if request.client else "unknown"


def per_ip(limiter: RateLimiter):
    """FastAPI dependency limiting a route per client IP."""

    def dependency(request: Request) -> None:
        limiter.hit(client_ip(request))

    return dependency


# One limiter per sensitive action. Values are deliberately generous for
# normal use and tight for brute force / email abuse.
login_ip_limiter = RateLimiter("login-ip", limit=20, window_seconds=300)
login_account_limiter = RateLimiter("login-account", limit=8, window_seconds=300)
signup_limiter = RateLimiter("signup", limit=10, window_seconds=3600)
email_action_ip_limiter = RateLimiter("email-ip", limit=10, window_seconds=900)
email_action_account_limiter = RateLimiter("email-account", limit=3, window_seconds=900)
refresh_limiter = RateLimiter("refresh", limit=60, window_seconds=60)
reset_limiter = RateLimiter("reset", limit=10, window_seconds=900)
oauth_limiter = RateLimiter("oauth", limit=30, window_seconds=300)

ALL_LIMITERS = [
    login_ip_limiter,
    login_account_limiter,
    signup_limiter,
    email_action_ip_limiter,
    email_action_account_limiter,
    refresh_limiter,
    reset_limiter,
    oauth_limiter,
]
