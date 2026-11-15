"""
Session, recovery, confirmation, OAuth, rate-limit and authorization tests.
Supabase is mocked; nothing here touches the network or a database.
"""

import os
import threading
import time
import uuid

os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "unit-test-secret-unit-test-secret-1234")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/reqintel_test")

import pytest
from fastapi.testclient import TestClient

import api.v1.auth as auth_api
import auth.service as auth_service_module
import core.dependencies as deps
import core.rate_limit as rl
from core.config import settings
from core.dependencies import get_user_db
from core.rate_limit import ALL_LIMITERS, RateLimiter
from core.supabase import create_auth_client, get_rules_client
from fakes import FakeAuthClient, api_error, install_fake_auth
from main import app
from test_auth import GOOD_PASSWORD, bearer, make_token  # noqa: F401

SIGNUP = {"email": "new@example.com", "password": GOOD_PASSWORD, "full_name": "New User"}
CHALLENGE = "A" * 43
VERIFIER = "v" * 64


@pytest.fixture(autouse=True)
def _reset_limits(monkeypatch):
    # Never call the real Supabase settings endpoint from tests: both
    # providers are "enabled" unless a test overrides this.
    monkeypatch.setattr(
        auth_service_module,
        "fetch_enabled_providers",
        lambda: {"google": True, "github": True, "email": True},
    )
    auth_service_module.reset_settings_cache()
    for limiter in ALL_LIMITERS:
        limiter.reset()
    yield
    for limiter in ALL_LIMITERS:
        limiter.reset()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake(monkeypatch):
    return install_fake_auth(monkeypatch)


@pytest.fixture
def active_user(monkeypatch):
    monkeypatch.setattr(deps, "fetch_user_profile",
                        lambda uid, tok: {"role": "business_analyst", "is_active": True})


@pytest.fixture
def inactive_user(monkeypatch):
    monkeypatch.setattr(deps, "fetch_user_profile",
                        lambda uid, tok: {"role": "business_analyst", "is_active": False})


# --------------------------------------------------------------------------
# Registration validation
# --------------------------------------------------------------------------

def test_full_name_of_150_chars_is_accepted(client, fake):
    r = client.post("/api/v1/auth/signup", json={**SIGNUP, "full_name": "a" * 150})
    assert r.status_code == 201


@pytest.mark.parametrize("length", [151, 200, 255, 400])
def test_full_name_over_150_chars_is_rejected(client, fake, length):
    r = client.post("/api/v1/auth/signup", json={**SIGNUP, "full_name": "a" * length})
    assert r.status_code == 422
    assert fake.calls == []  # never reached Supabase / the database trigger


def test_full_name_whitespace_is_collapsed_and_control_chars_rejected(client, fake):
    r = client.post("/api/v1/auth/signup", json={**SIGNUP, "full_name": "  Ada    Lovelace  "})
    assert r.status_code == 201
    assert fake.calls[0][1]["options"]["data"]["full_name"] == "Ada Lovelace"
    assert client.post("/api/v1/auth/signup",
                       json={**SIGNUP, "full_name": "Bad\x00Name"}).status_code == 422


@pytest.mark.parametrize("password", [
    "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere", "Sh0rt", "a" * 129 + "A1",
])
def test_weak_passwords_are_rejected(client, fake, password):
    assert client.post("/api/v1/auth/signup", json={**SIGNUP, "password": password}).status_code == 422
    assert fake.calls == []


def test_signup_normalises_email_and_sets_confirmation_redirect(client, fake):
    r = client.post("/api/v1/auth/signup", json={**SIGNUP, "email": "  New@Example.COM "})
    assert r.status_code == 201
    params = fake.calls[0][1]
    assert params["email"] == "new@example.com"
    assert params["options"]["email_redirect_to"] == f"{settings.frontend_url}/auth/callback"


def test_duplicate_registration_does_not_reveal_the_account(client, fake):
    fake.sign_up_error = api_error("User already registered", 422, "user_already_exists")
    dup = client.post("/api/v1/auth/signup", json=SIGNUP)

    fake.sign_up_error = None
    fresh = client.post("/api/v1/auth/signup", json=SIGNUP)

    assert dup.status_code == fresh.status_code == 201
    assert dup.json() == fresh.json()


def test_unknown_supabase_signup_error_is_generic_and_not_leaked(client, fake):
    fake.sign_up_error = api_error("Database error saving new user: secret detail", 500, "unexpected_failure")
    r = client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 400
    assert "secret" not in r.text and "Database" not in r.text


def test_signup_email_rate_limit_from_supabase_is_429(client, fake):
    fake.sign_up_error = api_error("email rate limit exceeded", 429, "over_email_send_rate_limit")
    assert client.post("/api/v1/auth/signup", json=SIGNUP).status_code == 429


# --------------------------------------------------------------------------
# Email confirmation / resend
# --------------------------------------------------------------------------

def test_unconfirmed_login_returns_403_with_code(client, fake):
    fake.sign_in_error = api_error("Email not confirmed", 400, "email_not_confirmed")
    r = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "Whatever1"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "email_not_confirmed"


def test_resend_confirmation_is_generic_for_any_email(client, fake):
    ok = client.post("/api/v1/auth/resend-confirmation", json={"email": "known@example.com"})
    fake.resend_error = api_error("User not found", 400, "user_not_found")
    unknown = client.post("/api/v1/auth/resend-confirmation", json={"email": "ghost@example.com"})
    assert ok.status_code == unknown.status_code == 200
    assert ok.json() == unknown.json()
    assert fake.calls[0][1]["type"] == "signup"


def test_resend_confirmation_is_rate_limited_per_account(client, fake):
    codes = [client.post("/api/v1/auth/resend-confirmation", json={"email": "x@example.com"}).status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


# --------------------------------------------------------------------------
# Login, inactive users, rate limiting
# --------------------------------------------------------------------------

def test_login_inactive_user_is_403_and_session_is_revoked(client, fake, inactive_user):
    r = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "Whatever1"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "account_disabled"
    assert fake.signed_out and fake.signed_out[0][1] == "local"


def test_login_user_without_profile_is_generic_401(client, fake, monkeypatch):
    monkeypatch.setattr(deps, "fetch_user_profile", lambda uid, tok: None)
    r = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "Whatever1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password."
    assert fake.signed_out


def test_inactive_user_is_rejected_on_every_protected_request(client, inactive_user):
    for path in ("/api/v1/auth/me", "/api/v1/projects"):
        r = client.get(path, headers=bearer(make_token()))
        assert r.status_code == 403, path
        assert r.json()["detail"]["code"] == "account_disabled"


def test_login_is_rate_limited_per_account(client, fake, active_user):
    body = {"email": "victim@example.com", "password": "Wrong-pass1"}
    fake.sign_in_error = api_error("Invalid login credentials", 400, "invalid_credentials")
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8
    assert codes[8:] == [429, 429]


def test_one_accounts_lockout_does_not_block_other_accounts(client, fake, active_user):
    fake.sign_in_error = api_error("Invalid login credentials", 400, "invalid_credentials")
    for _ in range(9):
        client.post("/api/v1/auth/login", json={"email": "victim@example.com", "password": "x"})
    fake.sign_in_error = None
    other = client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "x"})
    assert other.status_code == 200


def test_signup_is_rate_limited_per_ip(client, fake):
    codes = [client.post("/api/v1/auth/signup",
                         json={**SIGNUP, "email": f"u{i}@example.com"}).status_code for i in range(12)]
    assert codes[:10] == [201] * 10
    assert codes[10:] == [429, 429]


def test_rate_limited_response_has_retry_after(client, fake):
    for i in range(10):
        client.post("/api/v1/auth/signup", json={**SIGNUP, "email": f"u{i}@example.com"})
    r = client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_rate_limiter_window_expires(monkeypatch):
    limiter = RateLimiter("t", limit=2, window_seconds=10)
    clock = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock[0])
    limiter.hit("k"); limiter.hit("k")
    with pytest.raises(Exception) as exc:
        limiter.hit("k")
    assert exc.value.status_code == 429
    limiter.hit("other")  # separate key unaffected
    clock[0] += 11
    limiter.hit("k")  # window passed


# --------------------------------------------------------------------------
# Refresh + rotation + parallel requests
# --------------------------------------------------------------------------

def test_refresh_returns_new_rotated_pair(client, fake, active_user):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "old-refresh"})
    assert r.status_code == 200
    assert r.json()["access_token"] and r.json()["refresh_token"]
    assert fake.calls[0] == ("refresh_session", "old-refresh")


def test_refresh_token_cannot_be_reused_after_rotation(client, fake, active_user):
    fake.valid_refresh_tokens = {"r1"}
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": "r1"})
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": "r1"})
    assert first.status_code == 200
    assert second.status_code == 401


def test_refresh_failure_is_401_generic(client, fake):
    fake.refresh_error = api_error("Invalid Refresh Token", 400, "refresh_token_not_found")
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "bad"})
    assert r.status_code == 401
    assert "sign in again" in r.json()["detail"]


def test_refresh_for_inactive_user_is_403_and_revoked(client, fake, inactive_user):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "r"})
    assert r.status_code == 403
    assert fake.signed_out


def test_refresh_requires_a_token(client):
    assert client.post("/api/v1/auth/refresh", json={}).status_code == 422
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": ""}).status_code == 422


def test_parallel_refresh_calls_each_use_their_own_client(monkeypatch, active_user):
    created = []
    lock = threading.Lock()

    def factory():
        c = FakeAuthClient()
        with lock:
            created.append(c)
        return c

    monkeypatch.setattr(auth_api.auth_service, "client_factory", factory)
    tc = TestClient(app)
    statuses = []

    def go(i):
        statuses.append(tc.post("/api/v1/auth/refresh", json={"refresh_token": f"r{i}"}).status_code)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    [t.start() for t in threads]; [t.join() for t in threads]

    assert statuses == [200] * 20
    assert len(created) == 20 and len({id(c) for c in created}) == 20


# --------------------------------------------------------------------------
# Concurrent users / no shared auth state
# --------------------------------------------------------------------------

def test_auth_clients_are_never_shared():
    a, b = create_auth_client(), create_auth_client()
    assert a is not b
    assert a.auth is not b.auth


def test_rules_client_never_carries_a_user_token():
    before = dict(get_rules_client().headers)  # httpx lower-cases header names
    assert get_rules_client().headers["Authorization"] == f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    # Authenticated requests by two different users must not touch it.
    tc = TestClient(app)
    for tok in (make_token(sub=str(uuid.uuid4())), make_token(sub=str(uuid.uuid4()))):
        tc.get("/api/v1/auth/me", headers=bearer(tok))
    assert dict(get_rules_client().headers) == before


def test_per_request_db_clients_carry_only_their_own_token(monkeypatch):
    seen = {}
    real = deps._new_postgrest_client

    def spy(token):
        c = real(token)
        seen.setdefault(token, c.headers["Authorization"])
        return c

    monkeypatch.setattr(deps, "_new_postgrest_client", spy)

    class Creds:  # minimal HTTPAuthorizationCredentials stand-in
        def __init__(self, t): self.credentials = t

    results = {}

    def go(tok):
        gen = get_user_db(current_user=None, credentials=Creds(tok))
        client = next(gen)
        time.sleep(0.01)  # overlap the two "requests"
        results[tok] = client.headers["Authorization"]
        gen.close()

    t1, t2 = "token-user-A", "token-user-B"
    threads = [threading.Thread(target=go, args=(t,)) for t in (t1, t2)]
    [t.start() for t in threads]; [t.join() for t in threads]

    assert results[t1] == f"Bearer {t1}"
    assert results[t2] == f"Bearer {t2}"


def test_concurrent_logins_return_each_users_own_tokens(monkeypatch, active_user):
    def factory():
        c = FakeAuthClient()
        return c

    monkeypatch.setattr(auth_api.auth_service, "client_factory", factory)
    tc = TestClient(app)
    out = {}

    def go(i):
        r = tc.post("/api/v1/auth/login", json={"email": f"user{i}@example.com", "password": "Whatever1"})
        out[i] = r.status_code

    threads = [threading.Thread(target=go, args=(i,)) for i in range(15)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert set(out.values()) == {200}


# --------------------------------------------------------------------------
# Password recovery
# --------------------------------------------------------------------------

class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


def test_forgot_password_is_generic_and_sets_recovery_redirect(client, fake):
    a = client.post("/api/v1/auth/forgot-password", json={"email": "known@example.com"})
    fake.recover_error = api_error("User not found", 400, "user_not_found")
    b = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert fake.calls[0][2] == {"redirect_to": f"{settings.frontend_url}/reset-password"}


def test_forgot_password_validates_email_and_rate_limits(client, fake):
    assert client.post("/api/v1/auth/forgot-password", json={"email": "nope"}).status_code == 422
    codes = [client.post("/api/v1/auth/forgot-password", json={"email": "x@example.com"}).status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and 429 in codes[3:]


def test_reset_password_success(client, monkeypatch):
    sent = {}

    def put(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, json=json)
        return _Resp(200)

    monkeypatch.setattr(auth_service_module.httpx, "put", put)
    token = make_token()
    r = client.post("/api/v1/auth/reset-password", json={"access_token": token, "new_password": "BrandNew1pass"})
    assert r.status_code == 200
    assert sent["url"].endswith("/auth/v1/user")
    assert sent["headers"]["Authorization"] == f"Bearer {token}"
    assert sent["json"] == {"password": "BrandNew1pass"}


def test_reset_password_with_expired_token_never_calls_supabase(client, monkeypatch):
    monkeypatch.setattr(auth_service_module.httpx, "put",
                        lambda *a, **k: pytest.fail("must not be called"))
    now = int(time.time())
    expired = make_token(iat=now - 7200, exp=now - 3600)
    r = client.post("/api/v1/auth/reset-password", json={"access_token": expired, "new_password": "BrandNew1pass"})
    assert r.status_code == 400
    assert "invalid or has expired" in r.json()["detail"]


def test_reset_password_garbage_token_is_400(client):
    r = client.post("/api/v1/auth/reset-password", json={"access_token": "junk", "new_password": "BrandNew1pass"})
    assert r.status_code == 400


def test_reset_link_cannot_be_reused_once_supabase_rejects_it(client, monkeypatch):
    calls = iter([_Resp(200), _Resp(401, {"error_code": "bad_jwt"})])
    monkeypatch.setattr(auth_service_module.httpx, "put", lambda *a, **k: next(calls))
    body = {"access_token": make_token(), "new_password": "BrandNew1pass"}
    assert client.post("/api/v1/auth/reset-password", json=body).status_code == 200
    again = client.post("/api/v1/auth/reset-password", json=body)
    assert again.status_code == 400 and "expired" in again.json()["detail"]


def test_reset_password_same_as_old_is_reported(client, monkeypatch):
    monkeypatch.setattr(auth_service_module.httpx, "put",
                        lambda *a, **k: _Resp(422, {"error_code": "same_password"}))
    r = client.post("/api/v1/auth/reset-password",
                    json={"access_token": make_token(), "new_password": "BrandNew1pass"})
    assert r.status_code == 400 and "different" in r.json()["detail"]


@pytest.mark.parametrize("pw", ["short1A", "nouppercase1", "NOLOWERCASE1", "NoNumbersHere"])
def test_reset_password_enforces_password_policy(client, monkeypatch, pw):
    monkeypatch.setattr(auth_service_module.httpx, "put",
                        lambda *a, **k: pytest.fail("must not be called"))
    r = client.post("/api/v1/auth/reset-password", json={"access_token": make_token(), "new_password": pw})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# OAuth (Google / GitHub, PKCE)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("provider", ["google", "github"])
def test_oauth_url_for_supported_providers(client, provider):
    r = client.get(f"/api/v1/auth/oauth/{provider}/url", params={"code_challenge": CHALLENGE})
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith(f"{settings.SUPABASE_URL}/auth/v1/authorize?")
    assert f"provider={provider}" in url
    assert "code_challenge_method=s256" in url
    assert "redirect_to=" + "http%3A%2F%2Flocalhost%3A5173%2Fauth%2Fcallback" in url


@pytest.mark.parametrize("provider", ["microsoft", "azure", "facebook", "evil"])
def test_oauth_unsupported_providers_are_rejected(client, provider):
    assert client.get(f"/api/v1/auth/oauth/{provider}/url",
                      params={"code_challenge": CHALLENGE}).status_code == 422


@pytest.mark.parametrize("challenge", ["short", "A" * 44, "A" * 42 + "!"])
def test_oauth_invalid_code_challenge_rejected(client, challenge):
    assert client.get("/api/v1/auth/oauth/google/url", params={"code_challenge": challenge}).status_code == 422


def test_oauth_redirect_target_cannot_be_chosen_by_the_caller(client):
    r = client.get("/api/v1/auth/oauth/google/url",
                   params={"code_challenge": CHALLENGE, "redirect_to": "https://evil.example"})
    assert "evil.example" not in r.json()["url"]


def test_oauth_exchange_success_returns_tokens(client, fake, active_user):
    r = client.post("/api/v1/auth/oauth/exchange", json={"code": "abc", "code_verifier": VERIFIER})
    assert r.status_code == 200 and r.json()["access_token"] == "acc"
    assert fake.calls[0][1] == {"auth_code": "abc", "code_verifier": VERIFIER}


def test_oauth_exchange_failure_is_400_generic(client, fake):
    fake.exchange_error = api_error("invalid flow state", 400, "flow_state_not_found")
    r = client.post("/api/v1/auth/oauth/exchange", json={"code": "abc", "code_verifier": VERIFIER})
    assert r.status_code == 400 and "flow_state" not in r.text


def test_oauth_user_without_profile_gets_clear_email_hint(client, fake, monkeypatch):
    """GitHub account with no public email: the DB trigger cannot create the profile."""
    monkeypatch.setattr(deps, "fetch_user_profile", lambda uid, tok: None)
    r = client.post("/api/v1/auth/oauth/exchange", json={"code": "abc", "code_verifier": VERIFIER})
    assert r.status_code == 400 and "verified email" in r.json()["detail"]
    assert fake.signed_out


def test_oauth_inactive_user_is_403(client, fake, inactive_user):
    r = client.post("/api/v1/auth/oauth/exchange", json={"code": "abc", "code_verifier": VERIFIER})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "account_disabled"


@pytest.mark.parametrize("verifier", ["short", "x" * 129, "bad verifier with spaces " * 3])
def test_oauth_exchange_validates_verifier(client, fake, verifier):
    assert client.post("/api/v1/auth/oauth/exchange",
                       json={"code": "abc", "code_verifier": verifier}).status_code == 422


def test_oauth_users_follow_the_same_authorization_rules(client, monkeypatch):
    """An OAuth user is just a Supabase user: same JWT checks, same role gate."""
    monkeypatch.setattr(deps, "fetch_user_profile",
                        lambda uid, tok: {"role": "business_analyst", "is_active": True})
    tok = make_token(app_metadata={"provider": "github"})
    assert client.get("/api/v1/auth/me", headers=bearer(tok)).status_code == 200
    assert client.get("/api/v1/master/categories", headers=bearer(tok)).status_code == 403


# --------------------------------------------------------------------------
# Admin authorization and protected routes
# --------------------------------------------------------------------------

class _FakeDb:
    def from_(self, *_): return self
    def select(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def execute(self):
        class R: data = []
        return R()


def test_master_module_requires_authentication(client):
    assert client.get("/api/v1/master/categories").status_code == 401


def test_master_module_rejects_non_admins(client, active_user):
    assert client.get("/api/v1/master/categories", headers=bearer(make_token())).status_code == 403


def test_master_module_allows_admins(client, monkeypatch):
    monkeypatch.setattr(deps, "fetch_user_profile",
                        lambda uid, tok: {"role": "admin", "is_active": True})
    app.dependency_overrides[get_user_db] = lambda: _FakeDb()
    assert client.get("/api/v1/master/categories", headers=bearer(make_token())).status_code == 200


def test_deactivated_admin_loses_admin_access(client, monkeypatch):
    monkeypatch.setattr(deps, "fetch_user_profile",
                        lambda uid, tok: {"role": "admin", "is_active": False})
    assert client.get("/api/v1/master/categories", headers=bearer(make_token())).status_code == 403


def test_cors_allows_configured_frontend_origin():
    assert settings.frontend_url in settings.cors_origins


# --------------------------------------------------------------------------
# OAuth provider availability (Google / GitHub switched on in Supabase?)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("provider,label", [("google", "Google"), ("github", "GitHub")])
def test_disabled_provider_gives_clear_503_instead_of_a_raw_supabase_error(client, monkeypatch, provider, label):
    monkeypatch.setattr(auth_service_module, "fetch_enabled_providers",
                        lambda: {"google": False, "github": False, "email": True})
    r = client.get(f"/api/v1/auth/oauth/{provider}/url", params={"code_challenge": CHALLENGE})
    assert r.status_code == 503
    assert f"Sign-in with {label} is not enabled" in r.json()["detail"]


def test_only_the_disabled_provider_is_blocked(client, monkeypatch):
    monkeypatch.setattr(auth_service_module, "fetch_enabled_providers",
                        lambda: {"google": True, "github": False})
    assert client.get("/api/v1/auth/oauth/google/url", params={"code_challenge": CHALLENGE}).status_code == 200
    assert client.get("/api/v1/auth/oauth/github/url", params={"code_challenge": CHALLENGE}).status_code == 503


def test_unknown_provider_state_fails_open(client, monkeypatch):
    """If the settings check itself fails, Supabase decides; sign-in is never blocked by us."""
    monkeypatch.setattr(auth_service_module, "fetch_enabled_providers", lambda: None)
    assert client.get("/api/v1/auth/oauth/google/url", params={"code_challenge": CHALLENGE}).status_code == 200


class _SettingsResp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise auth_service_module.httpx.HTTPStatusError("x", request=None, response=None)

    def json(self):
        return self._body


def test_fetch_enabled_providers_reads_and_caches_supabase_settings(monkeypatch):
    monkeypatch.undo()  # use the real function, not the autouse stub
    auth_service_module.reset_settings_cache()
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return _SettingsResp({"external": {"google": True, "github": False, "email": True}})

    monkeypatch.setattr(auth_service_module.httpx, "get", get)

    first = auth_service_module.fetch_enabled_providers()
    second = auth_service_module.fetch_enabled_providers()

    assert first == second == {"google": True, "github": False, "email": True}
    assert len(calls) == 1  # cached
    assert calls[0][0].endswith("/auth/v1/settings")
    assert calls[0][1] == {"apikey": settings.SUPABASE_ANON_KEY}  # anon key only
    auth_service_module.reset_settings_cache()


def test_fetch_enabled_providers_returns_none_when_unreachable(monkeypatch):
    monkeypatch.undo()
    auth_service_module.reset_settings_cache()

    def get(*a, **k):
        raise auth_service_module.httpx.ConnectError("down")

    monkeypatch.setattr(auth_service_module.httpx, "get", get)
    assert auth_service_module.fetch_enabled_providers() is None
    auth_service_module.reset_settings_cache()


# --------------------------------------------------------------------------
# Sign-up failure diagnostics (the "400 Registration failed" case)
# --------------------------------------------------------------------------

def test_signup_failure_log_names_the_real_cause_but_no_secrets(client, fake, caplog):
    fake.sign_up_error = api_error("Something unexpected happened", 500, "unexpected_failure")
    with caplog.at_level("WARNING", logger="auth.service"):
        r = client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 400
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "code=unexpected_failure" in logged and "status=500" in logged
    assert "Something unexpected happened" in logged
    assert SIGNUP["password"] not in logged and SIGNUP["email"] not in logged


def test_smtp_failure_is_a_clear_503_not_a_misleading_400(client, fake):
    fake.sign_up_error = api_error("Error sending confirmation email", 500, "unexpected_failure")
    r = client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 503
    assert "couldn't send the confirmation email" in r.json()["detail"]


def test_profile_trigger_failure_is_explained_without_leaking_internals(client, fake):
    fake.sign_up_error = api_error("Database error saving new user", 500, "unexpected_failure")
    r = client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 400
    assert "could not be created" in r.json()["detail"]
    assert "Database" not in r.text


def test_signups_disabled_in_supabase_is_reported(client, fake):
    fake.sign_up_error = api_error("Signups not allowed", 422, "signup_disabled")
    r = client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 400 and "disabled" in r.json()["detail"]
