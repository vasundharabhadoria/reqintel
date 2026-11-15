"""
Module 1 authentication tests. No network and no database: Supabase calls are
mocked and tokens are minted locally with a dummy secret.
"""

import os
import time
import uuid

# Dummy settings, set BEFORE the app is imported, so these tests can never
# reach a real Supabase project even if a real backend/.env exists.
os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-key"
os.environ["SUPABASE_JWT_SECRET"] = "unit-test-secret-unit-test-secret-1234"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost:5432/reqintel_test"

import jwt
import pytest
from fastapi.testclient import TestClient

import api.v1.auth as auth_api
import core.dependencies as deps
from core.config import settings
from core.rate_limit import ALL_LIMITERS
from main import app

SECRET = settings.SUPABASE_JWT_SECRET
USER_ID = str(uuid.uuid4())


def make_token(**overrides):
    now = int(time.time())
    claims = {
        "sub": USER_ID,
        "email": "analyst@example.com",
        "aud": "authenticated",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, SECRET, algorithm="HS256")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate-limit state is per process; keep tests independent."""
    for limiter in ALL_LIMITERS:
        limiter.reset()
    yield
    for limiter in ALL_LIMITERS:
        limiter.reset()


@pytest.fixture
def known_user(monkeypatch):
    monkeypatch.setattr(
        deps,
        "fetch_user_profile",
        lambda uid, tok: {"role": "business_analyst", "is_active": True},
    )


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- protected endpoints ----------------

PROTECTED = [
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/projects"),
    ("POST", "/api/v1/projects"),
    ("GET", f"/api/v1/projects/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/projects/{uuid.uuid4()}"),
    ("POST", "/api/v1/projects/storage-cleanup/retry"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_no_token_is_401(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED)
def test_garbage_token_is_401(client, method, path):
    r = client.request(method, path, headers=bearer("not.a.jwt"))
    assert r.status_code == 401


def test_expired_token_is_401(client):
    now = int(time.time())
    token = make_token(iat=now - 7200, exp=now - 3600)
    r = client.get("/api/v1/projects", headers=bearer(token))
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_wrong_signature_is_401(client):
    token = jwt.encode({"sub": USER_ID, "email": "a@b.com", "aud": "authenticated",
                        "iss": settings.jwt_issuer, "exp": int(time.time()) + 600},
                       "some-other-secret-some-other-secret-12", algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_wrong_audience_is_401(client):
    assert client.get("/api/v1/auth/me", headers=bearer(make_token(aud="anon"))).status_code == 401


def test_wrong_issuer_is_401(client):
    assert client.get("/api/v1/auth/me", headers=bearer(make_token(iss="https://evil.example/auth/v1"))).status_code == 401


def test_unsigned_alg_none_token_is_401(client):
    token = jwt.encode({"sub": USER_ID, "email": "a@b.com", "aud": "authenticated",
                        "iss": settings.jwt_issuer, "exp": int(time.time()) + 600},
                       None, algorithm="none")
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_token_without_subject_is_401(client):
    assert client.get("/api/v1/auth/me", headers=bearer(make_token(sub=None))).status_code == 401


def test_token_without_email_is_401(client):
    assert client.get("/api/v1/auth/me", headers=bearer(make_token(email=None))).status_code == 401


def test_valid_token_returns_own_identity(client, known_user):
    r = client.get("/api/v1/auth/me", headers=bearer(make_token()))
    assert r.status_code == 200
    assert r.json() == {"id": USER_ID, "email": "analyst@example.com", "role": "business_analyst"}


def test_missing_profile_row_is_401_not_500(client, monkeypatch):
    monkeypatch.setattr(deps, "fetch_user_profile", lambda uid, tok: None)
    r = client.get("/api/v1/auth/me", headers=bearer(make_token()))
    assert r.status_code == 401


def test_role_lookup_failure_is_500(client, monkeypatch):
    def boom(uid, tok):
        raise RuntimeError("supabase down")
    monkeypatch.setattr(deps, "fetch_user_profile", boom)
    r = client.get("/api/v1/auth/me", headers=bearer(make_token()))
    assert r.status_code == 500


def test_profile_lookup_uses_per_request_client(monkeypatch):
    """The shared supabase client's headers must not carry the user's token
    because of the role lookup (concurrent requests would overwrite it)."""
    captured = {}

    class FakeResponse:
        data = [{"role": "business_analyst", "is_active": True}]

    class FakeQuery:
        def select(self, *_): return self
        def eq(self, *_): return self
        def limit(self, *_): return self
        def execute(self): return FakeResponse()

    class FakeSession:
        closed = False
        def close(self): FakeSession.closed = True

    class FakeClient:
        def __init__(self, url, headers=None, timeout=None):
            captured["headers"] = headers
            self.session = FakeSession()
        def from_(self, _): return FakeQuery()

    monkeypatch.setattr(deps, "SyncPostgrestClient", FakeClient)

    assert deps.fetch_user_profile("u1", "tok-A") == {
        "role": "business_analyst",
        "is_active": True,
    }
    assert captured["headers"]["Authorization"] == "Bearer tok-A"
    assert captured["headers"]["apikey"] == settings.SUPABASE_ANON_KEY
    assert FakeSession.closed is True


# ---------------- login / signup / logout (Supabase mocked) ----------------

from fakes import FakeAuthClient, install_fake_auth, api_error  # noqa: E402

GOOD_PASSWORD = "Longenough1"


@pytest.fixture
def fake_auth(monkeypatch):
    return install_fake_auth(monkeypatch)


def test_login_invalid_credentials_is_401_generic_message(client, fake_auth):
    fake_auth.sign_in_error = api_error("Invalid login credentials", 400, "invalid_credentials")

    r = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password."


def test_login_success_returns_tokens(client, fake_auth, known_user):
    r = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "correctpass1"})
    assert r.status_code == 200
    assert r.json()["access_token"] == "acc"
    assert r.json()["refresh_token"] == "ref"


def test_login_rejects_malformed_email(client):
    r = client.post("/api/v1/auth/login", json={"email": "nope", "password": "x"})
    assert r.status_code == 422


def test_signup_validation(client):
    ok = {"email": "new@example.com", "password": GOOD_PASSWORD, "full_name": "New User"}
    assert client.post("/api/v1/auth/signup", json={**ok, "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/signup", json={**ok, "email": "bad"}).status_code == 422
    assert client.post("/api/v1/auth/signup", json={**ok, "full_name": "A"}).status_code == 422


def test_signup_supabase_error_is_400(client, fake_auth):
    fake_auth.sign_up_error = api_error("Unable to validate email address", 400, "email_address_invalid")

    r = client.post("/api/v1/auth/signup",
                    json={"email": "dup@example.com", "password": GOOD_PASSWORD, "full_name": "Dup User"})
    assert r.status_code == 400


def test_signup_success_returns_generic_message(client, fake_auth):
    r = client.post("/api/v1/auth/signup",
                    json={"email": "new@example.com", "password": GOOD_PASSWORD, "full_name": "New User"})
    assert r.status_code == 201
    body = r.json()
    assert "confirmation link" in body["message"]
    assert "id" not in body and "email" not in body  # nothing about the account


def test_logout_requires_token(client):
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_logout_calls_supabase_with_token(client, known_user, fake_auth):
    token = make_token()
    r = client.post("/api/v1/auth/logout", headers=bearer(token))
    assert r.status_code == 200
    assert fake_auth.signed_out == [(token, "local")]
