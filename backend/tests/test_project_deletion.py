"""
Integration tests for permanent project deletion (Phase 1).

They run against a DISPOSABLE PostgreSQL database that has the ReqIntel
schema loaded (sql/02..12 plus the live repository_versions and
requirement_issue_waivers tables). They never touch Supabase: storage is
replaced by an in-memory fake and the database is a local throw-away copy.

Environment (defaults match the sandbox used to develop this feature):
    TEST_PG_HOST, TEST_PG_PORT, TEST_PG_DB, TEST_PG_PASSWORD

Run from the backend folder:
    python -m pytest tests/test_project_deletion.py -v
"""

import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

HOST = os.getenv("TEST_PG_HOST", "127.0.0.1")
PORT = int(os.getenv("TEST_PG_PORT", "5432"))
DB = os.getenv("TEST_PG_DB", "reqintel_test")
PW = os.getenv("TEST_PG_PASSWORD", "testpw")

# The app config needs these at import time. Real values are never used here
# (environment variables take priority over backend/.env).
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "a.b.c"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "a.b.c"
os.environ["SUPABASE_JWT_SECRET"] = "test-secret"
os.environ["DATABASE_URL"] = f"postgresql+asyncpg://postgres:{PW}@{HOST}:{PORT}/{DB}"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from auth.schemas import UserResponse  # noqa: E402
from services.project_deletion_service import ProjectDeletionService  # noqa: E402
from services.project_repository import ProjectRepository  # noqa: E402

pytestmark = pytest.mark.asyncio

MIGRATION = (
    Path(__file__).resolve().parent.parent.parent / "sql" / "15_permanent_delete.sql"
)
SRC = "requirement-sources"
REP = "reports"


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


class _Bucket:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def list(self, folder, opts=None):
        if self.owner.fail_list:
            raise Exception("list failed")
        opts = opts or {}
        limit, offset = opts.get("limit", 100), opts.get("offset", 0)
        prefix = folder.rstrip("/") + "/"
        names: dict = {}
        for p in sorted(self.owner.objects[self.name]):
            if p.startswith(prefix):
                rest = p[len(prefix):]
                head = rest.split("/", 1)[0]
                names[head] = None if "/" in rest else f"id-{p}"
        items = [{"name": n, "id": i} for n, i in names.items()]
        return items[offset : offset + limit]

    def remove(self, paths):
        if self.owner.fail_remove:
            raise Exception("storage down")
        for p in paths:
            self.owner.objects[self.name].discard(p)
        return [{"name": p} for p in paths]


class FakeStorage:
    def __init__(self):
        self.storage = self
        self.objects = {SRC: set(), REP: set()}
        self.fail_remove = False
        self.fail_list = False

    def from_(self, bucket):
        return _Bucket(self, bucket)

    def snapshot(self):
        return {k: set(v) for k, v in self.objects.items()}


async def admin_conn():
    return await asyncpg.connect(
        user="postgres", password=PW, host=HOST, port=PORT, database=DB
    )


def engine_for(role):
    return create_async_engine(
        f"postgresql+asyncpg://{role}:{PW}@{HOST}:{PORT}/{DB}", poolclass=NullPool
    )


async def session_for(engine, user_id) -> AsyncSession:
    """Mimics db.session.get_db: one session, RLS user set via set_config."""
    s = AsyncSession(engine, expire_on_commit=False)
    await s.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id)},
    )
    return s


async def seed_user(conn) -> UUID:
    uid = uuid4()
    await conn.execute(
        "INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES($1,$2,$3::jsonb)",
        uid,
        f"{uid}@test.local",
        json.dumps({"full_name": "Test User"}),
    )
    return uid


async def seed_project(conn, owner, storage, name="Hospital Management System",
                       full=True) -> dict:
    pid = uuid4()
    await conn.execute(
        "INSERT INTO projects(id,name,owner_id,project_type) VALUES($1,$2,$3,'Healthcare')",
        pid, name, owner,
    )
    await conn.execute(
        "INSERT INTO activity_logs(user_id,action,entity_type,entity_id) "
        "VALUES($1,'PROJECT_CREATED','project',$2)", owner, pid,
    )
    ids = {"project_id": pid}
    if not full:
        return ids

    s1, s2 = uuid4(), uuid4()
    path1 = f"{pid}/{s1}.pdf"
    await conn.execute(
        "INSERT INTO requirement_sources(id,project_id,source_type,original_filename,"
        "storage_path,uploaded_by) VALUES($1,$2,'pdf','spec.pdf',$3,$4)",
        s1, pid, path1, owner,
    )
    await conn.execute(
        "INSERT INTO requirement_sources(id,project_id,source_type,uploaded_by) "
        "VALUES($1,$2,'manual',$3)", s2, pid, owner,
    )
    storage.objects[SRC].add(path1)

    r1, r2 = uuid4(), uuid4()
    for rid, code, sid in ((r1, "REQ-001", s1), (r2, "REQ-002", s2)):
        await conn.execute(
            "INSERT INTO requirements(id,project_id,source_id,requirement_code,title,created_by) "
            "VALUES($1,$2,$3,$4,$4,$5)", rid, pid, sid, code, owner,
        )
    v1, v1b, v2 = uuid4(), uuid4(), uuid4()
    for vid, rid, n in ((v1, r1, 1), (v1b, r1, 2), (v2, r2, 1)):
        await conn.execute(
            "INSERT INTO requirement_versions(id,requirement_id,version_number,requirement_text,created_by) "
            "VALUES($1,$2,$3,'The system shall work.',$4)", vid, rid, n, owner,
        )
    await conn.execute(
        "INSERT INTO rule_validation(requirement_version_id,rule_name,passed) VALUES($1,'r1',false)", v1)
    aid = uuid4()
    await conn.execute(
        "INSERT INTO ai_analysis(id,requirement_version_id,model_name,prompt_type) "
        "VALUES($1,$2,'m','requirement_quality_analysis')", aid, v1b)
    await conn.execute(
        "INSERT INTO ai_suggestions(ai_analysis_id,suggestion_text,suggestion_type) "
        "VALUES($1,'fix it','other')", aid)
    await conn.execute(
        "INSERT INTO requirement_issue_waivers(requirement_version_id,rule_name) VALUES($1,'r1')", v1)
    await conn.execute(
        "INSERT INTO requirement_traceability(source_requirement_id,target_requirement_id,link_type) "
        "VALUES($1,$2,'depends_on')", r1, r2)

    mid, apid, tid = uuid4(), uuid4(), uuid4()
    await conn.execute("INSERT INTO modules(id,project_id,code,name) VALUES($1,$2,'M1','Mod')", mid, pid)
    await conn.execute(
        "INSERT INTO apis(id,project_id,module_id,http_method,endpoint_path) VALUES($1,$2,$3,'GET','/x')",
        apid, pid, mid)
    await conn.execute(
        "INSERT INTO test_cases(id,project_id,code,title) VALUES($1,$2,'T1','t')", tid, pid)
    await conn.execute(
        "INSERT INTO requirement_test_cases(requirement_id,test_case_id) VALUES($1,$2)", r1, tid)
    await conn.execute(
        "INSERT INTO change_impact_analysis(source_requirement_version_id,affected_requirement_id,"
        "affected_module_id,affected_api_id,affected_test_case_id,risk_level) "
        "VALUES($1,$2,$3,$4,$5,'high')", v1b, r2, mid, apid, tid)

    for fmt, ext in (("pdf", "pdf"), ("xlsx", "xlsx")):
        rid_ = uuid4()
        fp = f"{pid}/{rid_}.{ext}"
        await conn.execute(
            "INSERT INTO reports(id,project_id,generated_by,report_format,file_path) "
            "VALUES($1,$2,$3,$4,$5)", rid_, pid, owner, fmt, fp)
        storage.objects[REP].add(fp)

    for n in (1, 2, 3):
        await conn.execute(
            "INSERT INTO repository_versions(project_id,version_number,is_current,created_by) "
            "VALUES($1,$2,$3,$4)", pid, n, n == 3, owner)
    return ids


PROJECT_TABLES = {
    "projects": "id",
    "requirement_sources": "project_id",
    "requirements": "project_id",
    "modules": "project_id",
    "apis": "project_id",
    "test_cases": "project_id",
    "reports": "project_id",
    "repository_versions": "project_id",
}
CHILD_SQL = {
    "requirement_versions": "SELECT COUNT(*) FROM requirement_versions rv JOIN requirements r ON r.id=rv.requirement_id WHERE r.project_id=$1",
}


async def project_footprint(conn, pid) -> dict:
    out = {}
    for t, col in PROJECT_TABLES.items():
        out[t] = await conn.fetchval(f"SELECT COUNT(*) FROM {t} WHERE {col}=$1", pid)
    return out


async def all_rows(conn, table) -> int:
    return await conn.fetchval(f"SELECT COUNT(*) FROM {table}")


async def events(conn, action=None, pid=None):
    rows = await conn.fetch(
        "SELECT id,action,entity_id,details::text AS d FROM activity_logs "
        "WHERE ($1::text IS NULL OR action=$1) AND ($2::uuid IS NULL OR entity_id=$2) "
        "ORDER BY created_at", action, pid)
    return [(r["id"], r["action"], r["entity_id"], json.loads(r["d"]) if r["d"] else None) for r in rows]


@pytest_asyncio.fixture
async def admin():
    c = await admin_conn()
    yield c
    await c.close()


@pytest_asyncio.fixture(params=["postgres", "reqintel_app"])
async def env(request, admin):
    """Runs every test twice: as the bypass-RLS role and as reqintel_app."""
    if request.param == "reqintel_app":
        await admin.execute(MIGRATION.read_text())
    engine = engine_for(request.param)
    storage = FakeStorage()
    yield {"engine": engine, "storage": storage, "role": request.param}
    await engine.dispose()


async def delete(env, user, pid, name):
    s = await session_for(env["engine"], user)
    try:
        svc = ProjectDeletionService(s, storage_client=env["storage"])
        return await svc.permanently_delete_project(user, pid, name)
    finally:
        if s.in_transaction():
            await s.rollback()
        await s.close()


# ---------------------------------------------------------------------------
# Scenarios 1-8, 12, 13, 14
# ---------------------------------------------------------------------------


async def test_01_empty_project(env, admin):
    u = await seed_user(admin)
    p = (await seed_project(admin, u, env["storage"], full=False))["project_id"]
    res = await delete(env, u, p, "Hospital Management System")
    assert res.storage_cleanup.status == "not_required"
    assert all(v == 0 for v in (await project_footprint(admin, p)).values())


async def test_02_to_08_full_project(env, admin):
    storage = env["storage"]
    u = await seed_user(admin)
    other_user = await seed_user(admin)
    target = (await seed_project(admin, u, storage))["project_id"]
    bystander = (await seed_project(admin, u, storage, name="Other Project"))["project_id"]
    foreign = (await seed_project(admin, other_user, storage, name="Not Yours"))["project_id"]

    # an orphaned file: in storage under the project folder, in no DB row
    orphan = f"{target}/orphan-never-committed.pdf"
    storage.objects[SRC].add(orphan)

    by_before = await project_footprint(admin, bystander)
    events_before = {e[0] for e in await events(admin)}
    other_files = {b: {p for p in s if str(target) not in p} for b, s in storage.objects.items()}

    res = await delete(env, u, target, "Hospital Management System")

    # 2/3/4/5/6: all project data gone
    assert all(v == 0 for v in (await project_footprint(admin, target)).values())
    for sql in (
        "SELECT COUNT(*) FROM requirement_versions WHERE requirement_id NOT IN (SELECT id FROM requirements)",
        "SELECT COUNT(*) FROM rule_validation WHERE requirement_version_id NOT IN (SELECT id FROM requirement_versions)",
        "SELECT COUNT(*) FROM ai_analysis WHERE requirement_version_id NOT IN (SELECT id FROM requirement_versions)",
        "SELECT COUNT(*) FROM ai_suggestions WHERE ai_analysis_id NOT IN (SELECT id FROM ai_analysis)",
        "SELECT COUNT(*) FROM requirement_issue_waivers WHERE requirement_version_id NOT IN (SELECT id FROM requirement_versions)",
    ):
        assert await admin.fetchval(sql) == 0
    # 7: waivers / versions / analysis for the deleted project specifically
    assert res.deleted_counts["issue_waivers"] == 1
    assert res.deleted_counts["repository_versions"] == 3
    assert res.deleted_counts["requirement_versions"] == 3
    assert res.deleted_counts["ai_suggestions"] == 1
    assert res.deleted_counts["reports"] == 2

    # 8: storage removed (DB-referenced + orphan); other projects' files untouched
    left = storage.snapshot()
    assert not any(str(target) in p for s in left.values() for p in s)
    for b in other_files:
        assert other_files[b] <= left[b]
    assert res.storage_cleanup.status == "completed"
    assert res.storage_cleanup.total_files == 4  # 1 source + 2 reports + 1 orphan
    assert any(e[1] == "PROJECT_STORAGE_CLEANUP_COMPLETED" for e in await events(admin, pid=target))

    # bystander + foreign projects untouched
    assert await project_footprint(admin, bystander) == by_before
    assert (await project_footprint(admin, foreign))["requirements"] == 2

    # 12: history preserved, new audit event appended with the required fields
    after = await events(admin)
    assert events_before <= {e[0] for e in after}
    deleted_ev = [e for e in await events(admin, "PROJECT_PERMANENTLY_DELETED", target)]
    assert len(deleted_ev) == 1
    d = deleted_ev[0][3]
    assert d["project_id"] == str(target)
    assert d["project_name"] == "Hospital Management System"
    assert d["deleted_by"] == str(u)
    assert d["correlation_id"] == str(res.correlation_id)
    assert {"bucket": SRC, "path": orphan} in d["storage_objects"]
    assert any(e[1] == "PROJECT_CREATED" and e[2] == target for e in after)
    with pytest.raises(asyncpg.PostgresError):  # immutability triggers still active
        await admin.execute("DELETE FROM activity_logs WHERE entity_id=$1", target)
    with pytest.raises(asyncpg.PostgresError):
        await admin.execute("UPDATE activity_logs SET action='x' WHERE entity_id=$1", target)

    # 13: gone from listings
    s = await session_for(env["engine"], u)
    repo = ProjectRepository(s)
    assert await repo.get_by_id(target, u) is None
    assert target not in {r["id"] for r in await repo.list_for_owner(u, None, None)}
    assert bystander in {r["id"] for r in await repo.list_for_owner(u, None, None)}
    await s.rollback(); await s.close()

    # 14: re-creating a project with the same name starts with clean version data
    new_id = (await seed_project(admin, u, storage, full=False))["project_id"]
    assert new_id != target
    assert await admin.fetchval("SELECT COUNT(*) FROM repository_versions WHERE project_id=$1", new_id) == 0
    assert await admin.fetchval("SELECT COUNT(*) FROM repository_versions WHERE project_id=$1", target) == 0


async def test_unsafe_db_path_is_skipped_not_deleted(env, admin):
    storage = env["storage"]
    u = await seed_user(admin)
    a = (await seed_project(admin, u, storage))["project_id"]
    b = (await seed_project(admin, u, storage, name="B"))["project_id"]
    victim = f"{b}/victim.pdf"
    storage.objects[SRC].add(victim)
    # tampered row: points into ANOTHER project's folder
    await admin.execute(
        "UPDATE requirement_sources SET storage_path=$1 WHERE project_id=$2 AND storage_path IS NOT NULL",
        victim, a)
    await delete(env, u, a, "Hospital Management System")
    assert victim in storage.objects[SRC]
    d = (await events(admin, "PROJECT_PERMANENTLY_DELETED", a))[0][3]
    assert {"bucket": SRC, "path": victim} in d["skipped_objects"]


# ---------------------------------------------------------------------------
# Scenario 9: storage failure + retry
# ---------------------------------------------------------------------------


async def test_09_storage_failure_then_retry(env, admin):
    storage = env["storage"]
    u = await seed_user(admin)
    p = (await seed_project(admin, u, storage))["project_id"]
    storage.fail_remove = True

    res = await delete(env, u, p, "Hospital Management System")

    # DB deletion stands and is reported as success; cleanup is reported failed
    assert all(v == 0 for v in (await project_footprint(admin, p)).values())
    assert res.storage_cleanup.status == "failed"
    assert res.storage_cleanup.failed_files == 3
    assert "retried" in res.message
    assert any(str(p) in x for s in storage.objects.values() for x in s)
    failed_ev = await events(admin, "PROJECT_STORAGE_CLEANUP_FAILED", p)
    assert len(failed_ev) == 1 and len(failed_ev[0][3]["failed_objects"]) == 3
    assert not await events(admin, "PROJECT_STORAGE_CLEANUP_COMPLETED", p)

    # retry while storage is still down: stays pending, nothing lost
    s = await session_for(env["engine"], u)
    r = await ProjectDeletionService(s, storage_client=storage).retry_storage_cleanup(u)
    assert r.pending_found == 1 and r.still_failing == 1
    await s.close()

    # storage recovers: retry works although the project row no longer exists
    storage.fail_remove = False
    s = await session_for(env["engine"], u)
    r = await ProjectDeletionService(s, storage_client=storage).retry_storage_cleanup(
        u, res.correlation_id)
    await s.close()
    assert r.completed == 1 and r.still_failing == 0
    assert not any(str(p) in x for s_ in storage.objects.values() for x in s_)
    assert len(await events(admin, "PROJECT_STORAGE_CLEANUP_COMPLETED", p)) == 1

    # nothing pending afterwards; another user can never see/retry it
    s = await session_for(env["engine"], u)
    r = await ProjectDeletionService(s, storage_client=storage).retry_storage_cleanup(u)
    await s.close()
    assert r.pending_found == 0
    stranger = await seed_user(admin)
    s = await session_for(env["engine"], stranger)
    r = await ProjectDeletionService(s, storage_client=storage).retry_storage_cleanup(stranger)
    await s.close()
    assert r.pending_found == 0


async def test_listing_failure_does_not_block_deletion(env, admin):
    storage = env["storage"]
    u = await seed_user(admin)
    p = (await seed_project(admin, u, storage))["project_id"]
    storage.fail_list = True
    res = await delete(env, u, p, "Hospital Management System")
    assert all(v == 0 for v in (await project_footprint(admin, p)).values())
    assert res.storage_cleanup.total_files == 3  # DB-recorded paths still cleaned
    d = (await events(admin, "PROJECT_PERMANENTLY_DELETED", p))[0][3]
    assert set(d["storage_listing_errors"]) == {SRC, REP}


# ---------------------------------------------------------------------------
# Scenarios 10, 11 and guards
# ---------------------------------------------------------------------------


async def test_10_other_users_project_cannot_be_deleted(env, admin):
    storage = env["storage"]
    owner, attacker = await seed_user(admin), await seed_user(admin)
    p = (await seed_project(admin, owner, storage))["project_id"]
    before, files = await project_footprint(admin, p), storage.snapshot()
    with pytest.raises(HTTPException) as e:
        await delete(env, attacker, p, "Hospital Management System")
    assert e.value.status_code == 404
    assert await project_footprint(admin, p) == before
    assert storage.snapshot() == files
    assert not await events(admin, "PROJECT_PERMANENTLY_DELETED", p)


async def test_wrong_confirmation_name_deletes_nothing(env, admin):
    storage = env["storage"]
    u = await seed_user(admin)
    p = (await seed_project(admin, u, storage))["project_id"]
    before = await project_footprint(admin, p)
    with pytest.raises(HTTPException) as e:
        await delete(env, u, p, "hospital management system")  # wrong case
    assert e.value.status_code == 400
    assert await project_footprint(admin, p) == before


async def test_double_delete_is_404(env, admin):
    u = await seed_user(admin)
    p = (await seed_project(admin, u, env["storage"]))["project_id"]
    await delete(env, u, p, "Hospital Management System")
    with pytest.raises(HTTPException) as e:
        await delete(env, u, p, "Hospital Management System")
    assert e.value.status_code == 404


async def test_11_db_failure_rolls_back_everything(env, admin):
    storage = env["storage"]
    u = await seed_user(admin)
    p = (await seed_project(admin, u, storage))["project_id"]
    before, files = await project_footprint(admin, p), storage.snapshot()
    ev_before = len(await events(admin))
    await admin.execute(
        "CREATE OR REPLACE FUNCTION fn_test_fail() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'simulated failure'; END $$ LANGUAGE plpgsql")
    await admin.execute(
        "CREATE TRIGGER trg_test_fail BEFORE DELETE ON modules "
        "FOR EACH ROW EXECUTE FUNCTION fn_test_fail()")
    try:
        with pytest.raises(HTTPException) as e:
            await delete(env, u, p, "Hospital Management System")
        assert e.value.status_code == 500
        assert "No data was changed" in e.value.detail
    finally:
        await admin.execute("DROP TRIGGER trg_test_fail ON modules")
    # reports, requirements, sources... were deleted BEFORE the failure: all restored
    assert await project_footprint(admin, p) == before
    assert storage.snapshot() == files  # storage untouched
    assert len(await events(admin)) == ev_before  # no audit event
    # a retry after the cause is fixed succeeds
    res = await delete(env, u, p, "Hospital Management System")
    assert res.storage_cleanup.status == "completed"


async def test_missing_delete_policy_is_detected_and_rolled_back(admin):
    """As reqintel_app WITHOUT sql/15: DELETE would silently remove 0 rows."""
    await admin.execute(
        "DROP POLICY IF EXISTS projects_delete_own ON projects;"
        "DROP POLICY IF EXISTS reports_delete_own_project ON reports;")
    engine, storage = engine_for("reqintel_app"), FakeStorage()
    env_ = {"engine": engine, "storage": storage}
    u = await seed_user(admin)
    p = (await seed_project(admin, u, storage))["project_id"]
    before, files = await project_footprint(admin, p), storage.snapshot()
    try:
        with pytest.raises(HTTPException) as e:
            await delete(env_, u, p, "Hospital Management System")
        assert e.value.status_code == 500 and "15_permanent_delete" in e.value.detail
        assert await project_footprint(admin, p) == before
        assert storage.snapshot() == files
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


async def test_http_endpoints(env, admin, monkeypatch):
    import core.storage as core_storage
    from api.v1.projects import router
    from core.dependencies import get_current_user
    from db.session import get_db

    monkeypatch.setattr(core_storage, "_storage_client", env["storage"])
    owner, stranger = await seed_user(admin), await seed_user(admin)
    p = (await seed_project(admin, owner, env["storage"]))["project_id"]

    app = FastAPI()
    app.include_router(router)
    current = {"id": owner}

    def fake_user():
        return UserResponse(id=str(current["id"]), email="x@y.z", role="business_analyst")

    async def fake_db():
        s = await session_for(env["engine"], current["id"])
        try:
            yield s
        finally:
            if s.in_transaction():
                await s.rollback()
            await s.close()

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    transport = httpx.ASGITransport(app=app)
    url = f"/api/v1/projects/{p}/permanent"
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.request("DELETE", url)                       # missing body
        assert r.status_code == 422
        r = await c.request("DELETE", url, json={"confirm_name": "nope"})
        assert r.status_code == 400
        current["id"] = stranger                                   # not the owner
        r = await c.request("DELETE", url, json={"confirm_name": "Hospital Management System"})
        assert r.status_code == 404
        assert (await project_footprint(admin, p))["projects"] == 1
        current["id"] = owner
        r = await c.request("DELETE", url, json={"confirm_name": "Hospital Management System"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["project_id"] == str(p) and body["storage_cleanup"]["status"] == "completed"
        r = await c.post("/api/v1/projects/storage-cleanup/retry")
        assert r.status_code == 200 and r.json()["pending_found"] == 0

    # archive endpoint contract unchanged (still a DELETE on /{id}, not permanent)
    paths = {(r_.path, tuple(sorted(r_.methods))) for r_ in router.routes}
    assert ("/api/v1/projects/{project_id}", ("DELETE",)) in paths


async def test_unauthenticated_request_rejected():
    from api.v1.projects import router

    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.request("DELETE", f"/api/v1/projects/{uuid4()}/permanent",
                            json={"confirm_name": "x"})
        assert r.status_code == 401
        r = await c.post("/api/v1/projects/storage-cleanup/retry")
        assert r.status_code == 401
