"""
Persistence tests for project create / update / archive / restore.

They prove COMMIT behaviour, not just HTTP status codes: after every API call
the row is looked up through a SEPARATE database connection (asyncpg, as the
postgres superuser), so uncommitted data can never be seen by accident.

The request path under test is real: FastAPI route -> db.session.get_db ->
ProjectService -> ProjectRepository -> PostgreSQL. Only the Supabase JWT check
(get_current_user) is replaced, because it needs the network.

Needs the same disposable PostgreSQL as test_project_deletion.py (see its
header). NEVER point TEST_PG_* at a live database.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importing this module also sets the dummy SUPABASE_*/DATABASE_URL env vars
# that the app configuration needs at import time.
import test_project_deletion as base
from test_project_deletion import admin_conn, engine_for, seed_user  # noqa: E402

from fastapi import FastAPI  # noqa: E402

from auth.schemas import UserResponse  # noqa: E402
from core.dependencies import get_current_user  # noqa: E402
from models.project import ProjectResponse  # noqa: E402

pytestmark = pytest.mark.asyncio

BACKEND = Path(__file__).resolve().parent.parent


@pytest_asyncio.fixture
async def admin():
    c = await admin_conn()
    yield c
    await c.close()


@pytest_asyncio.fixture(params=["postgres", "reqintel_app"])
async def app_ctx(request, admin, monkeypatch):
    """
    Real app + real get_db. The app's session factory is pointed at the
    disposable DB (NullPool so connections never cross event loops) as the
    chosen role: `postgres` bypasses RLS, `reqintel_app` does not.
    """
    import db.session as session_module

    if request.param == "reqintel_app":
        await admin.execute(base.MIGRATION.read_text(encoding="utf-8"))

    engine = engine_for(request.param)
    monkeypatch.setattr(
        session_module,
        "AsyncSessionLocal",
        async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False),
    )

    from api.v1.projects import router

    user = await seed_user(admin)
    current = {"id": user}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(current["id"]), email="t@example.com", role="business_analyst"
    )

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=bool(os.getenv("T_RAISE")))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        yield {"client": client, "user": user, "current": current, "role": request.param}

    await engine.dispose()


async def row(admin, pid):
    return await admin.fetchrow(
        "SELECT id,name,client_name,project_type,description,status::text AS status,"
        "owner_id,updated_at FROM projects WHERE id=$1", UUID(str(pid)))


async def log_actions(admin, pid):
    return [r["action"] for r in await admin.fetch(
        "SELECT action FROM activity_logs WHERE entity_id=$1 ORDER BY created_at", UUID(str(pid)))]


async def create(ctx, name=None):
    r = await ctx["client"].post("/api/v1/projects", json={
        "name": name or f"Persist-{uuid4().hex[:8]}",
        "client_name": "ACME", "project_type": "Healthcare", "description": "d"})
    assert r.status_code == 201, r.text
    return r.json()


FAIL_LOG_TRIGGER = (
    "CREATE OR REPLACE FUNCTION fn_test_fail_log() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'simulated activity-log failure'; END $$ LANGUAGE plpgsql;"
    "CREATE TRIGGER trg_test_fail_log BEFORE INSERT ON activity_logs "
    "FOR EACH ROW EXECUTE FUNCTION fn_test_fail_log();"
)


class failing_activity_log:
    """Context manager: every activity_logs INSERT raises while active."""

    def __init__(self, admin):
        self.admin = admin

    async def __aenter__(self):
        await self.admin.execute(FAIL_LOG_TRIGGER)

    async def __aexit__(self, *exc):
        await self.admin.execute("DROP TRIGGER IF EXISTS trg_test_fail_log ON activity_logs")


# ---------------------------------------------------------------------------
# 1-3  create is committed and visible from a separate session; log persists
# ---------------------------------------------------------------------------


async def test_create_is_committed_and_visible_to_another_session(app_ctx, admin):
    body = await create(app_ctx)
    pid = body["id"]

    stored = await row(admin, pid)                      # separate connection
    assert stored is not None, "project row was NOT committed"
    assert stored["name"] == body["name"] and stored["status"] == "active"
    assert stored["owner_id"] == app_ctx["user"]
    assert await log_actions(admin, pid) == ["PROJECT_CREATED"]

    # the owner's own RLS-scoped view (second, independent request/session)
    r = await app_ctx["client"].get(f"/api/v1/projects/{pid}")
    assert r.status_code == 200 and r.json()["id"] == pid
    r = await app_ctx["client"].get("/api/v1/projects")
    assert pid in {p["id"] for p in r.json()["items"]}


async def test_create_response_format_unchanged(app_ctx):
    body = await create(app_ctx)
    assert set(body) == set(ProjectResponse.model_fields)
    assert body["status"] == "active" and body["owner_id"] == str(app_ctx["user"])


# ---------------------------------------------------------------------------
# 6  atomicity: failed activity-log insert leaves NO partial project
# ---------------------------------------------------------------------------


async def test_failed_activity_log_leaves_no_project(app_ctx, admin):
    name = f"Atomic-{uuid4().hex[:8]}"
    async with failing_activity_log(admin):
        r = await app_ctx["client"].post("/api/v1/projects", json={"name": name})
    assert r.status_code == 500
    assert await admin.fetchval("SELECT COUNT(*) FROM projects WHERE name=$1", name) == 0
    # and a retry once the cause is gone works
    body = await create(app_ctx, name)
    assert await row(admin, body["id"]) is not None


# ---------------------------------------------------------------------------
# 7  update / archive / restore / status change
# ---------------------------------------------------------------------------


async def test_update_persists(app_ctx, admin):
    pid = (await create(app_ctx))["id"]
    before = await row(admin, pid)
    r = await app_ctx["client"].put(f"/api/v1/projects/{pid}", json={
        "name": "Renamed", "client_name": "New Client", "project_type": "Telecom", "description": "x"})
    assert r.status_code == 200, r.text
    after = await row(admin, pid)
    assert (after["name"], after["client_name"], after["project_type"]) == ("Renamed", "New Client", "Telecom")
    assert after["updated_at"] > before["updated_at"]
    assert (await log_actions(admin, pid))[-1] == "PROJECT_UPDATED"


async def test_archive_and_restore_persist(app_ctx, admin):
    pid = (await create(app_ctx))["id"]
    c = app_ctx["client"]

    r = await c.delete(f"/api/v1/projects/{pid}")
    assert r.status_code == 200 and r.json()["status"] == "archived"
    assert (await row(admin, pid))["status"] == "archived"

    r = await c.patch(f"/api/v1/projects/{pid}/status", json={"status": "active"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert (await row(admin, pid))["status"] == "active"

    assert await log_actions(admin, pid) == [
        "PROJECT_CREATED", "PROJECT_ARCHIVED", "PROJECT_STATUS_CHANGED"]


@pytest.mark.parametrize("op", ["update", "archive", "status"])
async def test_failed_activity_log_rolls_back_changes(app_ctx, admin, op):
    pid = (await create(app_ctx, f"Keep-{uuid4().hex[:8]}"))["id"]
    before = await row(admin, pid)
    calls = {
        "update": lambda c: c.put(f"/api/v1/projects/{pid}", json={"name": "SHOULD-NOT-STICK"}),
        "archive": lambda c: c.delete(f"/api/v1/projects/{pid}"),
        "status": lambda c: c.patch(f"/api/v1/projects/{pid}/status", json={"status": "suspended"}),
    }
    async with failing_activity_log(admin):
        r = await calls[op](app_ctx["client"])
    assert r.status_code == 500
    assert dict(await row(admin, pid)) == dict(before)          # nothing changed
    assert await log_actions(admin, pid) == ["PROJECT_CREATED"]


async def test_other_users_project_untouched_and_404(app_ctx, admin):
    pid = (await create(app_ctx))["id"]
    before = dict(await row(admin, pid))
    app_ctx["current"]["id"] = await seed_user(admin)           # a different user
    c = app_ctx["client"]
    assert (await c.put(f"/api/v1/projects/{pid}", json={"name": "hijack"})).status_code == 404
    assert (await c.delete(f"/api/v1/projects/{pid}")).status_code == 404
    assert (await c.patch(f"/api/v1/projects/{pid}/status", json={"status": "archived"})).status_code == 404
    assert dict(await row(admin, pid)) == before


# ---------------------------------------------------------------------------
# 4-5  restart the backend: a REAL uvicorn process, killed and started again
# ---------------------------------------------------------------------------


def _free_port():
    """Ask the OS for an unused TCP port (a fresh one per test, so a port that
    Windows is slow to release can never break the next run)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_backend(role, port):
    env = dict(os.environ)
    env["DATABASE_URL"] = (
        f"postgresql+asyncpg://{role}:{base.PW}@{base.HOST}:{base.PORT}/{base.DB}"
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.persistence_app:app",
         "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/openapi.json", timeout=1)
            return proc
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError(proc.stdout.read().decode())
            time.sleep(0.3)
    proc.kill()
    raise RuntimeError("backend did not start")


def _stop_backend(proc, mode):
    """
    Stop the backend with the portable subprocess API (no `signal` module).

    terminate -> Popen.terminate(): SIGTERM on Linux/macOS, so uvicorn runs its
                 normal shutdown. On Windows this is TerminateProcess, i.e. a
                 hard stop.
    kill      -> Popen.kill(): SIGKILL on Linux/macOS (no shutdown hooks, like
                 a crash or OOM kill); TerminateProcess on Windows.

    Both modes run on every platform. On Windows they behave the same, which
    is fine here: the assertion is that committed data survives either way.
    """
    if mode == "kill":
        proc.kill()
    else:
        proc.terminate()

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()  # never leave a server running
        proc.wait(timeout=15)


@pytest.mark.parametrize("mode", ["terminate", "kill"])
@pytest.mark.parametrize("role", ["postgres", "reqintel_app"])
async def test_project_survives_backend_restart(admin, role, mode):
    if role == "reqintel_app":
        await admin.execute(base.MIGRATION.read_text(encoding="utf-8"))
    user = await seed_user(admin)
    hdr = {"X-Test-User": str(user)}
    port = _free_port()

    p1 = _start_backend(role, port)
    try:
        r = httpx.post(f"http://127.0.0.1:{port}/api/v1/projects", headers=hdr,
                       json={"name": f"Restart-{uuid4().hex[:6]}", "client_name": "C"})
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        assert await row(admin, pid) is not None            # visible right away
    finally:
        _stop_backend(p1, mode)

    assert p1.poll() is not None                            # first backend is gone
    assert await row(admin, pid) is not None                # still in the DB

    p2 = _start_backend(role, port)                         # brand-new process
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/api/v1/projects/{pid}", headers=hdr)
        assert r.status_code == 200 and r.json()["id"] == pid
        listed = httpx.get(f"http://127.0.0.1:{port}/api/v1/projects", headers=hdr).json()
        assert pid in {p["id"] for p in listed["items"]}
    finally:
        _stop_backend(p2, "terminate")
    assert await log_actions(admin, pid) == ["PROJECT_CREATED"]