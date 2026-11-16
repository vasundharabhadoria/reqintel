"""
Profile and permanent account deletion, tested end to end.

Real PostgreSQL (the disposable reqintel_test database, queried as the
RLS-enforced `reqintel_app` role), real JWT verification, real FK / trigger
behaviour. Only Supabase Auth and Storage are replaced:

  * FakeAdminClient.delete_user performs a REAL `DELETE FROM auth.users`, so
    the cascade to public.users and every RESTRICT / SET NULL rule runs.
  * Storage is the in-memory FakeStorage used by the project-deletion tests.

sql/17_account_deletion_prereq.sql is applied to the throw-away database for
these tests. It has NOT been applied to the live Supabase project.
"""

import asyncio
import time
import uuid
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends
from supabase_auth.errors import AuthApiError

import api.v1.auth as auth_api
import core.dependencies as deps
from auth.account_service import (
    AccountDeletionService,
    auth_providers,
    last_authentication_time,
    reauth_method,
)
from auth.schemas import UserResponse
from core.dependencies import get_current_user
from core.rate_limit import ALL_LIMITERS
from db.session import get_db
from fakes import _Result, _Session, _User, api_error, install_fake_auth
from main import app
from test_auth import make_token
from test_project_deletion import (
    REP,
    SRC,
    FakeStorage,
    admin_conn,
    engine_for,
    project_footprint,
    seed_project,
    seed_user,
    session_for,
)

pytestmark = pytest.mark.asyncio

MIG15 = Path(__file__).resolve().parents[2] / "sql" / "15_permanent_delete.sql"
MIG17 = Path(__file__).resolve().parents[2] / "sql" / "17_account_deletion_prereq.sql"
LEGACY_TRIGGER = """
DROP TRIGGER IF EXISTS trg_activitylogs_block_update ON public.activity_logs;
CREATE TRIGGER trg_activitylogs_block_update BEFORE UPDATE ON public.activity_logs
    FOR EACH ROW EXECUTE FUNCTION public.fn_block_row_update();
"""
PASSWORD = "Str0ngPassw0rd"
URL = "/api/v1/auth"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeAdminClient:
    """auth.admin.delete_user that runs a real DELETE on auth.users."""

    def __init__(self) -> None:
        self.auth = self
        self.admin = self
        self.deleted: list[str] = []
        self.error: Exception | None = None

    def delete_user(self, user_id: str) -> None:
        if self.error:
            raise self.error

        async def _delete():
            conn = await admin_conn()
            try:
                await conn.execute("DELETE FROM auth.users WHERE id = $1", UUID(user_id))
            finally:
                await conn.close()

        asyncio.run(_delete())  # runs in the service's worker thread
        self.deleted.append(user_id)


def _lookup_profile(user_id: str, _token: str):
    """Stand-in for the PostgREST profile read in get_current_user."""

    async def _query():
        conn = await admin_conn()
        try:
            row = await conn.fetchrow(
                "SELECT role::text AS role, is_active FROM users WHERE id = $1",
                UUID(user_id),
            )
            return dict(row) if row else None
        finally:
            await conn.close()

    return asyncio.run(_query())


def token_for(user_id, email, *, provider="email", providers=None, signed_in_ago=5, **extra):
    return make_token(
        sub=str(user_id),
        email=email,
        app_metadata={"provider": provider, "providers": providers or [provider]},
        amr=[{"method": "password", "timestamp": int(time.time()) - signed_in_ago}],
        **extra,
    )


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def email_of(admin, user_id):
    return await admin.fetchval("SELECT email::text FROM users WHERE id = $1", user_id)


class Ctx:
    def __init__(self, http, admin, storage, admin_client, passwords, fake_auth):
        self.http, self.admin, self.storage = http, admin, storage
        self.admin_client, self.passwords, self.fake_auth = admin_client, passwords, fake_auth

    async def user(self, password=PASSWORD):
        uid = await seed_user(self.admin)
        email = f"user-{uid}@example.com"  # `.local` is rejected by EmailStr
        await self.admin.execute("UPDATE auth.users SET email=$2 WHERE id=$1", uid, email)
        await self.admin.execute("UPDATE public.users SET email=$2 WHERE id=$1", uid, email)
        self.passwords[email] = (str(uid), password)
        return uid, email

    async def delete(self, token, **body):
        body = {"confirmation": "DELETE", "password": PASSWORD, **body}
        body = {k: v for k, v in body.items() if v is not None}
        return await self.http.request("DELETE", f"{URL}/account", json=body, headers=auth(token))

    async def user_exists(self, uid):
        return bool(await self.admin.fetchval("SELECT count(*) FROM auth.users WHERE id=$1", uid)) , bool(
            await self.admin.fetchval("SELECT count(*) FROM public.users WHERE id=$1", uid)
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin():
    conn = await admin_conn()
    await conn.execute(MIG15.read_text())
    await conn.execute(MIG17.read_text())
    yield conn
    await conn.execute(MIG17.read_text())  # leave the shared test DB as found
    await conn.close()


@pytest_asyncio.fixture
async def ctx(admin, monkeypatch):
    for limiter in ALL_LIMITERS:
        limiter.reset()

    engine = engine_for("reqintel_app")  # RLS applies, like production
    storage, admin_client, passwords = FakeStorage(), FakeAdminClient(), {}
    fake_auth = install_fake_auth(monkeypatch)

    def sign_in(creds):
        known = passwords.get(creds["email"])
        if not known or known[1] != creds["password"]:
            raise api_error("Invalid login credentials", 400, "invalid_credentials")
        return _Result(
            user=_User(creds["email"], known[0]),
            session=_Session(*fake_auth.next_tokens()),
        )

    fake_auth.auth.sign_in_with_password = sign_in

    async def _get_db(current_user: UserResponse = Depends(get_current_user)):
        session = await session_for(engine, current_user.id)
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()
            await session.close()

    real_service = AccountDeletionService
    monkeypatch.setattr(
        auth_api,
        "AccountDeletionService",
        lambda db, auth_service: real_service(
            db,
            auth_service=auth_service,
            admin_client_factory=lambda: admin_client,
            storage_client=storage,
        ),
    )
    monkeypatch.setattr(deps, "fetch_user_profile", _lookup_profile)
    app.dependency_overrides[get_db] = _get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield Ctx(http, admin, storage, admin_client, passwords, fake_auth)

    app.dependency_overrides.clear()
    await engine.dispose()
    for limiter in ALL_LIMITERS:
        limiter.reset()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


async def test_provider_and_reauth_helpers():
    assert auth_providers({}) == ("email", ["email"])
    assert auth_providers({"app_metadata": {"provider": "google", "providers": ["google"]}}) == (
        "google",
        ["google"],
    )
    assert reauth_method(["google"]) == "recent_login"
    assert reauth_method(["google", "email"]) == "password"
    assert last_authentication_time({}) is None
    assert last_authentication_time({"amr": [{"timestamp": 5}, {"timestamp": 9}, "junk"]}) == 9


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def test_fetch_own_profile(ctx):
    uid, email = await ctx.user()
    res = await ctx.http.get(f"{URL}/profile", headers=auth(token_for(uid, email)))
    body = res.json()

    assert res.status_code == 200
    assert body["id"] == str(uid) and body["email"] == email
    assert body["full_name"] == "Test User" and body["role"] == "business_analyst"
    assert body["is_active"] is True and body["created_at"]
    assert body["auth_provider"] == "email" and body["reauth_method"] == "password"


async def test_oauth_profile_reports_provider(ctx):
    uid, email = await ctx.user()
    token = token_for(uid, email, provider="github")
    body = (await ctx.http.get(f"{URL}/profile", headers=auth(token))).json()
    assert body["auth_provider"] == "github" and body["reauth_method"] == "recent_login"


async def test_update_own_full_name(ctx):
    uid, email = await ctx.user()
    other, _ = await ctx.user()
    res = await ctx.http.patch(
        f"{URL}/profile", json={"full_name": "  Asha   Verma "}, headers=auth(token_for(uid, email))
    )

    assert res.status_code == 200 and res.json()["full_name"] == "Asha Verma"
    assert await ctx.admin.fetchval("SELECT full_name FROM users WHERE id=$1", uid) == "Asha Verma"
    # another user's profile is untouched
    assert await ctx.admin.fetchval("SELECT full_name FROM users WHERE id=$1", other) == "Test User"


@pytest.mark.parametrize(
    "field,value",
    [("role", "admin"), ("is_active", False), ("email", "x@y.io"), ("id", str(uuid.uuid4()))],
)
async def test_protected_fields_are_rejected(ctx, field, value):
    uid, email = await ctx.user()
    before = await ctx.admin.fetchrow("SELECT * FROM users WHERE id=$1", uid)

    res = await ctx.http.patch(
        f"{URL}/profile",
        json={"full_name": "Valid Name", field: value},
        headers=auth(token_for(uid, email)),
    )

    assert res.status_code == 422
    assert await ctx.admin.fetchrow("SELECT * FROM users WHERE id=$1", uid) == before


@pytest.mark.parametrize("bad", ["", " ", "A", "x" * 151, "Bad\u0000Name", "Tab\u200bName"])
async def test_invalid_full_name_is_rejected(ctx, bad):
    uid, email = await ctx.user()
    res = await ctx.http.patch(
        f"{URL}/profile", json={"full_name": bad}, headers=auth(token_for(uid, email))
    )
    assert res.status_code == 422
    assert await ctx.admin.fetchval("SELECT full_name FROM users WHERE id=$1", uid) == "Test User"


async def test_profile_requires_authentication(ctx):
    uid, email = await ctx.user()
    expired = token_for(uid, email, exp=int(time.time()) - 600)

    for headers in ({}, auth("not-a-jwt"), auth(expired)):
        assert (await ctx.http.get(f"{URL}/profile", headers=headers)).status_code == 401
        assert (await ctx.http.patch(f"{URL}/profile", json={"full_name": "Valid"}, headers=headers)).status_code == 401
        assert (await ctx.http.request("DELETE", f"{URL}/account", json={"confirmation": "DELETE"}, headers=headers)).status_code == 401

    assert (await ctx.user_exists(uid)) == (True, True)


async def test_inactive_account_cannot_use_profile(ctx):
    uid, email = await ctx.user()
    await ctx.admin.execute("UPDATE users SET is_active=false WHERE id=$1", uid)
    res = await ctx.http.get(f"{URL}/profile", headers=auth(token_for(uid, email)))
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Account deletion — happy path and isolation
# ---------------------------------------------------------------------------


async def test_successful_deletion_cleans_everything_and_spares_others(ctx):
    a, a_email = await ctx.user()
    b, _ = await ctx.user()
    a1 = (await seed_project(ctx.admin, a, ctx.storage, name="Alpha"))["project_id"]
    a2 = (await seed_project(ctx.admin, a, ctx.storage, name="Beta (archived)"))["project_id"]
    await ctx.admin.execute("UPDATE projects SET status='archived' WHERE id=$1", a2)
    b1 = (await seed_project(ctx.admin, b, ctx.storage, name="Bee"))["project_id"]

    b_rows = await project_footprint(ctx.admin, b1)
    b_files = {k: {p for p in v if str(b1) in p} for k, v in ctx.storage.objects.items()}
    others_before = {
        "auth_users": await ctx.admin.fetchval("SELECT count(*) FROM auth.users WHERE id <> $1", a),
        "users": await ctx.admin.fetchval("SELECT count(*) FROM public.users WHERE id <> $1", a),
        "projects": await ctx.admin.fetchval("SELECT count(*) FROM projects WHERE owner_id <> $1", a),
        "logs": await ctx.admin.fetchval("SELECT count(*) FROM activity_logs WHERE user_id IS DISTINCT FROM $1 AND user_id IS NOT NULL", a),
    }
    logs_before = await ctx.admin.fetchval("SELECT count(*) FROM activity_logs WHERE user_id=$1", a)
    assert logs_before > 0

    res = await ctx.delete(token_for(a, a_email))
    body = res.json()

    assert res.status_code == 200, body
    assert body["projects_deleted"] == 2 and body["storage_files_removed"] == 6

    # identity + profile gone
    assert (await ctx.user_exists(a)) == (False, False)
    assert ctx.admin_client.deleted == [str(a)]
    # every row of both projects (incl. the archived one) is gone, no orphans
    for pid in (a1, a2):
        assert all(v == 0 for v in (await project_footprint(ctx.admin, pid)).values())
    for sql in (
        "SELECT count(*) FROM requirement_versions WHERE requirement_id NOT IN (SELECT id FROM requirements)",
        "SELECT count(*) FROM reports WHERE project_id NOT IN (SELECT id FROM projects)",
        "SELECT count(*) FROM requirement_sources WHERE project_id NOT IN (SELECT id FROM projects)",
        "SELECT count(*) FROM repository_versions WHERE project_id NOT IN (SELECT id FROM projects)",
    ):
        assert await ctx.admin.fetchval(sql) == 0
    # storage cleaned for A, untouched for B
    for bucket in (SRC, REP):
        assert not any(str(p).startswith((str(a1), str(a2))) for p in ctx.storage.objects[bucket])
        assert {p for p in ctx.storage.objects[bucket] if str(b1) in p} == b_files[bucket]
    # B and shared/global data intact
    assert await project_footprint(ctx.admin, b1) == b_rows
    assert (await ctx.user_exists(b)) == (True, True)
    assert others_before == {
        "auth_users": await ctx.admin.fetchval("SELECT count(*) FROM auth.users"),
        "users": await ctx.admin.fetchval("SELECT count(*) FROM public.users"),
        "projects": await ctx.admin.fetchval("SELECT count(*) FROM projects"),
        "logs": await ctx.admin.fetchval("SELECT count(*) FROM activity_logs WHERE user_id IS NOT NULL"),
    }
    # audit trail kept but anonymised
    assert await ctx.admin.fetchval("SELECT count(*) FROM activity_logs WHERE user_id=$1", a) == 0
    assert await ctx.admin.fetchval(
        "SELECT count(*) FROM activity_logs WHERE user_id IS NULL AND entity_id = ANY($1::uuid[])", [a1, a2]
    ) >= logs_before
    # the password check left no session behind
    token = [t for t, _ in ctx.fake_auth.signed_out]
    assert len(token) == 1


async def test_user_with_no_projects_can_delete(ctx):
    uid, email = await ctx.user()
    res = await ctx.delete(token_for(uid, email))
    assert res.status_code == 200 and res.json()["projects_deleted"] == 0
    assert (await ctx.user_exists(uid)) == (False, False)


async def test_cannot_delete_another_users_account(ctx):
    a, a_email = await ctx.user()
    b, _ = await ctx.user()
    await seed_project(ctx.admin, b, ctx.storage, name="B-project")

    # the API has no way to name another account...
    for extra in ({"user_id": str(b)}, {"id": str(b)}, {"email": "b@x.io"}):
        res = await ctx.delete(token_for(a, a_email), **extra)
        assert res.status_code == 422

    # ...and a real deletion by A never touches B
    assert (await ctx.delete(token_for(a, a_email))).status_code == 200
    assert (await ctx.user_exists(b)) == (True, True)
    assert await ctx.admin.fetchval("SELECT count(*) FROM projects WHERE owner_id=$1", b) == 1


async def test_confirmation_must_be_exact(ctx):
    uid, email = await ctx.user()
    for bad in ("delete", "Delete", "DELETE ", "", None):
        body = {"password": PASSWORD}
        if bad is not None:
            body["confirmation"] = bad
        res = await ctx.http.request("DELETE", f"{URL}/account", json=body, headers=auth(token_for(uid, email)))
        assert res.status_code == 422
    assert (await ctx.user_exists(uid)) == (True, True)


# ---------------------------------------------------------------------------
# Re-authentication
# ---------------------------------------------------------------------------


async def test_wrong_or_missing_password_is_refused(ctx):
    uid, email = await ctx.user()
    await seed_project(ctx.admin, uid, ctx.storage)
    token = token_for(uid, email)

    wrong = await ctx.delete(token, password="WrongPassw0rd")
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "reauth_failed"

    missing = await ctx.delete(token, password=None)
    assert missing.status_code == 403 and missing.json()["detail"]["code"] == "reauth_required"

    assert await ctx.admin.fetchval("SELECT count(*) FROM projects WHERE owner_id=$1", uid) == 1
    assert (await ctx.user_exists(uid)) == (True, True)


async def test_password_of_a_different_account_is_refused(ctx):
    a, a_email = await ctx.user(password="AlicePassw0rd")
    _, b_email = await ctx.user(password="BobPassw0rd")
    # A's token + B's password: the check always uses the TOKEN's email
    res = await ctx.delete(token_for(a, a_email), password="BobPassw0rd")
    assert res.status_code == 403
    assert (await ctx.user_exists(a)) == (True, True)


async def test_oauth_user_needs_a_recent_sign_in(ctx):
    uid, email = await ctx.user()
    stale = token_for(uid, email, provider="google", signed_in_ago=3600)
    res = await ctx.delete(stale, password=None)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "reauth_required"
    assert "Google" in res.json()["detail"]["message"]
    assert (await ctx.user_exists(uid)) == (True, True)

    fresh = token_for(uid, email, provider="google", signed_in_ago=30)
    assert (await ctx.delete(fresh, password=None)).status_code == 200
    assert (await ctx.user_exists(uid)) == (False, False)


async def test_oauth_token_without_amr_is_treated_as_stale(ctx):
    uid, email = await ctx.user()
    token = make_token(sub=str(uid), email=email, app_metadata={"provider": "github", "providers": ["github"]})
    res = await ctx.delete(token, password=None)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "reauth_required"


async def test_delete_attempts_are_rate_limited(ctx):
    uid, email = await ctx.user()
    token = token_for(uid, email)
    codes = [(await ctx.delete(token, password="WrongPassw0rd")).status_code for _ in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
    assert (await ctx.user_exists(uid)) == (True, True)


# ---------------------------------------------------------------------------
# Failure handling and retries
# ---------------------------------------------------------------------------


async def test_storage_failure_keeps_the_account_then_retry_succeeds(ctx):
    uid, email = await ctx.user()
    pid = (await seed_project(ctx.admin, uid, ctx.storage))["project_id"]
    token = token_for(uid, email)
    ctx.storage.fail_remove = True

    res = await ctx.delete(token)
    assert res.status_code == 502 and res.json()["detail"]["code"] == "storage_cleanup_incomplete"
    # DB rows are gone, the account is kept, files are still recoverable
    assert all(v == 0 for v in (await project_footprint(ctx.admin, pid)).values())
    assert (await ctx.user_exists(uid)) == (True, True)
    assert any(str(pid) in p for p in ctx.storage.objects[SRC])

    ctx.storage.fail_remove = False
    res = await ctx.delete(token)
    assert res.status_code == 200
    assert not any(str(pid) in p for b in ctx.storage.objects.values() for p in b)
    assert (await ctx.user_exists(uid)) == (False, False)


async def test_auth_admin_failure_is_reported_and_retry_succeeds(ctx):
    uid, email = await ctx.user()
    pid = (await seed_project(ctx.admin, uid, ctx.storage))["project_id"]
    token = token_for(uid, email)
    ctx.admin_client.error = AuthApiError("boom", 500, "unexpected_failure")

    res = await ctx.delete(token)
    assert res.status_code == 502 and res.json()["detail"]["code"] == "auth_delete_failed"
    assert all(v == 0 for v in (await project_footprint(ctx.admin, pid)).values())
    assert (await ctx.user_exists(uid)) == (True, True)

    ctx.admin_client.error = None
    assert (await ctx.delete(token)).status_code == 200
    assert (await ctx.user_exists(uid)) == (False, False)


async def test_without_the_activity_log_migration_deletion_fails_safely(ctx):
    """The live database today: this is exactly why sql/17 is required."""

    uid, email = await ctx.user()
    await seed_project(ctx.admin, uid, ctx.storage)
    token = token_for(uid, email)
    await ctx.admin.execute(LEGACY_TRIGGER)

    res = await ctx.delete(token)
    assert res.status_code == 502 and res.json()["detail"]["code"] == "auth_delete_failed"
    assert (await ctx.user_exists(uid)) == (True, True)  # nothing half-deleted at identity level

    await ctx.admin.execute(MIG17.read_text())  # apply the migration, then retry
    assert (await ctx.delete(token)).status_code == 200
    assert (await ctx.user_exists(uid)) == (False, False)


async def test_auth_user_already_gone_counts_as_success(ctx):
    uid, email = await ctx.user()
    ctx.admin_client.error = AuthApiError("User not found", 404, "user_not_found")
    assert (await ctx.delete(token_for(uid, email))).status_code == 200


async def test_remaining_restricted_references_block_deletion(ctx, monkeypatch):
    uid, email = await ctx.user()
    from auth.profile_repository import ProfileRepository

    async def leftovers(self, user_id):
        return {"reports": 1, "projects": 0}

    monkeypatch.setattr(ProfileRepository, "count_blocking_references", leftovers)
    res = await ctx.delete(token_for(uid, email))
    assert res.status_code == 409 and res.json()["detail"]["code"] == "account_has_remaining_data"
    assert ctx.admin_client.deleted == []


async def test_duplicate_deletion_is_harmless(ctx):
    uid, email = await ctx.user()
    token = token_for(uid, email)

    assert (await ctx.delete(token)).status_code == 200
    again = await ctx.delete(token)  # token still verifies, but the user is gone
    assert again.status_code == 401
    assert (await ctx.http.get(f"{URL}/profile", headers=auth(token))).status_code == 401
    assert ctx.admin_client.deleted == [str(uid)]


async def test_database_is_consistent_after_many_deletions(ctx):
    users = [await ctx.user() for _ in range(3)]
    for uid, _ in users:
        await seed_project(ctx.admin, uid, ctx.storage, name=f"P-{uid}")
    survivor, _ = await ctx.user()
    keep = (await seed_project(ctx.admin, survivor, ctx.storage, name="Keep"))["project_id"]

    for uid, email in users:
        assert (await ctx.delete(token_for(uid, email))).status_code == 200

    # no row anywhere still points at a deleted user
    for table, col in (
        ("projects", "owner_id"), ("requirement_sources", "uploaded_by"), ("requirements", "created_by"),
        ("requirement_versions", "created_by"), ("reports", "generated_by"),
        ("repository_versions", "created_by"), ("activity_logs", "user_id"),
    ):
        dangling = await ctx.admin.fetchval(
            f"SELECT count(*) FROM {table} t WHERE t.{col} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM public.users u WHERE u.id = t.{col})"
        )
        assert dangling == 0, table
    assert await ctx.admin.fetchval("SELECT count(*) FROM projects WHERE id=$1", keep) == 1
