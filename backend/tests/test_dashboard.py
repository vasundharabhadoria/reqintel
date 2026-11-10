"""
Dashboard API tests (Module 1). They run against the DISPOSABLE PostgreSQL
database described in tests/README.md, once as the bypass-RLS role and once
as reqintel_app. They never touch Supabase.

    python -m pytest tests/test_dashboard.py -v
"""

import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

import test_project_deletion as base  # sets the dummy app environment first
from test_project_deletion import admin_conn, engine_for, seed_user  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from auth.schemas import UserResponse  # noqa: E402
from core.dependencies import get_current_user  # noqa: E402
from sqlalchemy import text  # noqa: E402

pytestmark = pytest.mark.asyncio

GOOD = dict(clarity="Good", completeness="Good", unambiguity="Good",
            consistency="Good", specificity="Good", testability="Good")


def ts(value):
    """asyncpg needs datetime objects, not strings."""
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def qa(**overrides):
    return {**GOOD, **overrides}


@pytest_asyncio.fixture
async def admin():
    c = await admin_conn()
    yield c
    await c.close()


@pytest_asyncio.fixture(params=["postgres", "reqintel_app"])
async def client_for(request, admin, monkeypatch):
    """Returns client_for(user_id) -> httpx client authenticated as that user."""

    engine = engine_for(request.param)

    import db.session as session_module
    from api.v1.dashboard import router
    from db.session import get_db

    clients = []

    def make(user_id):
        app = FastAPI()
        app.include_router(router)

        async def current_user():
            return UserResponse(id=str(user_id), email="t@example.com", role="business_analyst")

        async def db_dep():
            s = AsyncSession(engine, expire_on_commit=False)
            await s.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(user_id)},
            )
            try:
                yield s
            finally:
                await s.rollback()
                await s.close()

        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_db] = db_dep
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        clients.append(c)
        return c

    yield make

    for c in clients:
        await c.aclose()
    await engine.dispose()


async def add_project(conn, owner, name="P", status="active"):
    pid = uuid4()
    await conn.execute(
        "INSERT INTO projects(id,name,owner_id,status) VALUES($1,$2,$3,$4::project_status_enum)",
        pid, name, owner, status,
    )
    return pid


async def add_source(conn, pid, owner):
    sid = uuid4()
    await conn.execute(
        "INSERT INTO requirement_sources(id,project_id,source_type,uploaded_by) "
        "VALUES($1,$2,'manual',$3)", sid, pid, owner)
    return sid


async def add_requirement(conn, pid, sid, owner, code, status="pending"):
    rid = uuid4()
    await conn.execute(
        "INSERT INTO requirements(id,project_id,source_id,requirement_code,title,status,created_by) "
        "VALUES($1,$2,$3,$4,$4,$5::requirement_status_enum,$6)", rid, pid, sid, code, status, owner)
    return rid


async def add_version(conn, rid, n, owner):
    vid = uuid4()
    await conn.execute(
        "INSERT INTO requirement_versions(id,requirement_id,version_number,requirement_text,created_by) "
        "VALUES($1,$2,$3,'The system shall work.',$4)", vid, rid, n, owner)
    return vid


async def add_analysis(conn, vid, assessment, suggestions=0, prompt="requirement_quality_analysis",
                       created="2026-01-01T00:00:00+00"):
    aid = uuid4()
    raw = json.dumps({"quality_assessment": assessment}) if assessment is not None else json.dumps({})
    await conn.execute(
        "INSERT INTO ai_analysis(id,requirement_version_id,model_name,prompt_type,raw_response_json,created_at) "
        "VALUES($1,$2,'m',$3,$4::jsonb,$5)", aid, vid, prompt, raw, ts(created))
    for i in range(suggestions):
        await conn.execute(
            "INSERT INTO ai_suggestions(ai_analysis_id,suggestion_text,suggestion_type) "
            "VALUES($1,$2,'other')", aid, f"s{i}")
    return aid


async def log(conn, owner, action, pid=None, details=None, at=None):
    await conn.execute(
        "INSERT INTO activity_logs(user_id,action,entity_type,entity_id,details,created_at) "
        "VALUES($1,$2,'project',$3,$4::jsonb,COALESCE($5, now()))",
        owner, action, pid, json.dumps(details) if details else None, ts(at))


async def summary(client, **params):
    r = await client.get("/api/v1/dashboard/summary", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------


async def test_new_user_gets_empty_state_not_fabricated_numbers(admin, client_for):
    u = await seed_user(admin)
    s = await summary(client_for(u))

    assert s["total_projects"] == 0 and s["active_projects"] == 0
    assert s["total_requirements"] == 0 and s["pending_reviews"] == 0
    assert s["ai_suggestions_generated"] == 0
    assert s["quality"] == {"score": None, "analysed_requirements": 0, "total_requirements": 0}
    assert s["recent_activity"] == []


async def test_counts_and_ownership(admin, client_for):
    me, other = await seed_user(admin), await seed_user(admin)

    p1 = await add_project(admin, me, "A", "active")
    p2 = await add_project(admin, me, "B", "archived")
    await add_project(admin, me, "C", "active")
    po = await add_project(admin, other, "Other", "active")

    s1 = await add_source(admin, p1, me)
    s2 = await add_source(admin, p2, me)
    so = await add_source(admin, po, other)

    r1 = await add_requirement(admin, p1, s1, me, "REQ-1", "pending")
    r2 = await add_requirement(admin, p1, s1, me, "REQ-2", "approved")
    r3 = await add_requirement(admin, p2, s2, me, "REQ-3", "pending")   # archived project still counts
    ro = await add_requirement(admin, po, so, other, "REQ-9", "pending")

    v1 = await add_version(admin, r1, 1, me)
    v3 = await add_version(admin, r3, 1, me)
    vo = await add_version(admin, ro, 1, other)
    await add_analysis(admin, v1, qa(), suggestions=3)
    await add_analysis(admin, v3, qa(), suggestions=2)
    await add_analysis(admin, vo, qa(), suggestions=7)   # other user's suggestions

    s = await summary(client_for(me))
    assert s["total_projects"] == 3
    assert s["active_projects"] == 2
    assert s["total_requirements"] == 3
    assert s["pending_reviews"] == 2
    assert s["ai_suggestions_generated"] == 5

    so_ = await summary(client_for(other))
    assert so_["total_projects"] == 1
    assert so_["total_requirements"] == 1
    assert so_["ai_suggestions_generated"] == 7


async def test_quality_calculation_exact(admin, client_for):
    u = await seed_user(admin)
    p = await add_project(admin, u)
    sid = await add_source(admin, p, u)

    # all Good = 100
    ra = await add_requirement(admin, p, sid, u, "REQ-1")
    # 2 Good, 2 Needs improvement, 2 Poor = (200+100+0)/6 = 50
    rb = await add_requirement(admin, p, sid, u, "REQ-2")
    # no analysis at all
    await add_requirement(admin, p, sid, u, "REQ-3")

    await add_analysis(admin, await add_version(admin, ra, 1, u), qa())
    await add_analysis(admin, await add_version(admin, rb, 1, u), qa(
        clarity="Good", completeness="Good",
        unambiguity="Needs improvement", consistency="Needs improvement",
        specificity="Poor", testability="Poor"))

    s = await summary(client_for(u))
    assert s["quality"]["analysed_requirements"] == 2
    assert s["quality"]["total_requirements"] == 3
    assert s["quality"]["score"] == 75.0          # (100 + 50) / 2


async def test_only_current_version_and_latest_analysis_count(admin, client_for):
    u = await seed_user(admin)
    p = await add_project(admin, u)
    sid = await add_source(admin, p, u)
    r = await add_requirement(admin, p, sid, u, "REQ-1")

    v1 = await add_version(admin, r, 1, u)
    v2 = await add_version(admin, r, 2, u)

    poor = qa(**{k: "Poor" for k in GOOD})
    # Old version analysed as Poor: must be ignored once v2 exists.
    await add_analysis(admin, v1, poor)

    s = await summary(client_for(u))
    assert s["quality"]["analysed_requirements"] == 0        # current version has no analysis yet
    assert s["quality"]["score"] is None

    # Two analyses on the current version: older Poor, newer Good -> newest wins.
    await add_analysis(admin, v2, poor, created="2026-02-01T00:00:00+00")
    await add_analysis(admin, v2, qa(), created="2026-03-01T00:00:00+00")

    s = await summary(client_for(u))
    assert s["quality"]["analysed_requirements"] == 1
    assert s["quality"]["score"] == 100.0


async def test_malformed_or_other_prompt_analyses_are_not_counted(admin, client_for):
    u = await seed_user(admin)
    p = await add_project(admin, u)
    sid = await add_source(admin, p, u)

    partial = {k: v for k, v in GOOD.items() if k != "testability"}
    unknown = qa(clarity="Excellent")
    for i, bad in enumerate((partial, unknown, None), start=1):
        r = await add_requirement(admin, p, sid, u, f"REQ-{i}")
        await add_analysis(admin, await add_version(admin, r, 1, u), bad)

    r = await add_requirement(admin, p, sid, u, "REQ-9")
    await add_analysis(admin, await add_version(admin, r, 1, u), qa(), prompt="traceability_suggestion")

    s = await summary(client_for(u))
    assert s["quality"]["analysed_requirements"] == 0
    assert s["quality"]["score"] is None
    assert s["quality"]["total_requirements"] == 4


async def test_activity_feed_real_events_scoped_and_ordered(admin, client_for):
    me, other = await seed_user(admin), await seed_user(admin)
    p = await add_project(admin, me, "Lounge Booking System")
    po = await add_project(admin, other, "Secret Project")

    await log(admin, me, "PROJECT_CREATED", p, at="2026-05-01T10:00:00+00")
    await log(admin, me, "PROJECT_UPDATED", p, at="2026-05-02T10:00:00+00")
    await log(admin, me, "REPORT_GENERATED", p, {"report_format": "pdf"}, at="2026-05-03T10:00:00+00")
    await log(admin, me, "LOGIN", None, at="2026-05-04T10:00:00+00")             # not a dashboard event
    await log(admin, other, "PROJECT_CREATED", po, at="2026-05-05T10:00:00+00")  # someone else's

    feed = (await summary(client_for(me)))["recent_activity"]

    assert [a["action"] for a in feed] == ["REPORT_GENERATED", "PROJECT_UPDATED", "PROJECT_CREATED"]
    assert feed[0]["label"] == "Report generated"
    assert feed[0]["detail"] == "PDF report"
    assert all(a["project_name"] == "Lounge Booking System" for a in feed)
    assert all(a["project_id"] == str(p) for a in feed)
    assert "Secret Project" not in json.dumps(feed)

    limited = (await summary(client_for(me), activity_limit=2))["recent_activity"]
    assert len(limited) == 2


async def test_deleted_project_event_keeps_logged_name(admin, client_for):
    u = await seed_user(admin)
    gone = uuid4()
    await log(admin, u, "PROJECT_PERMANENTLY_DELETED", gone, {"project_name": "Old System"})

    feed = (await summary(client_for(u)))["recent_activity"]
    assert len(feed) == 1
    assert feed[0]["project_name"] == "Old System"
    assert feed[0]["label"] == "Project permanently deleted"


async def test_activity_does_not_invent_history(admin, client_for):
    """A project with no log rows must not produce a fabricated 'created' event."""
    u = await seed_user(admin)
    await add_project(admin, u, "Silent")
    assert (await summary(client_for(u)))["recent_activity"] == []


async def test_activity_limit_validated(admin, client_for):
    u = await seed_user(admin)
    c = client_for(u)
    assert (await c.get("/api/v1/dashboard/summary", params={"activity_limit": 0})).status_code == 422
    assert (await c.get("/api/v1/dashboard/summary", params={"activity_limit": 51})).status_code == 422


async def test_score_function_edge_cases():
    from services.dashboard_service import score_quality_assessment as f

    assert f(GOOD) == 100
    assert f(qa(clarity=" good ")) == 100                 # trimmed, case-insensitive
    assert f({k: "Poor" for k in GOOD}) == 0
    assert f(None) is None and f("Good") is None and f([]) is None
    assert f(qa(clarity=5)) is None