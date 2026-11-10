"""
Regression tests: text extraction and requirement extraction must PERSIST.

get_db() rolls back any transaction still open when the request ends, so a
service method that writes without committing silently loses its changes
while still answering 200. These tests mimic get_db's session handling and
check the result from a separate connection.

    python -m pytest tests/test_source_extraction_persistence.py -v
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import test_project_deletion as base  # sets the dummy app environment first
from test_project_deletion import admin_conn, engine_for, seed_user  # noqa: E402

from services.requirement_service import RequirementService  # noqa: E402

pytestmark = pytest.mark.asyncio

SRS_TEXT = (
    "REQ-001 The system shall allow a customer to book a lounge slot.\n"
    "REQ-002 The system shall send a confirmation email within 60 seconds.\n"
)


class FakeStorage:
    def __init__(self, data=None, fail=False):
        self.storage = self
        self._data, self._fail = data, fail

    def from_(self, _bucket):
        return self

    def download(self, _path):
        if self._fail:
            raise RuntimeError("storage down")
        return self._data


class FakeExtraction:
    def identify_structured(self, content):
        reqs = [SimpleNamespace(text=l.split(" ", 1)[1]) for l in content.splitlines() if l.strip()]
        return SimpleNamespace(requirements=reqs, is_srs=True)


@pytest_asyncio.fixture
async def admin():
    c = await admin_conn()
    yield c
    await c.close()


@pytest_asyncio.fixture(params=["postgres", "reqintel_app"])
async def engine(request):
    e = engine_for(request.param)
    yield e
    await e.dispose()


async def seed(admin, with_text=False):
    owner = await seed_user(admin)
    pid, sid = uuid4(), uuid4()
    await admin.execute(
        "INSERT INTO projects(id,name,owner_id) VALUES($1,'P',$2)", pid, owner)
    await admin.execute(
        "INSERT INTO requirement_sources(id,project_id,source_type,original_filename,"
        "storage_path,uploaded_by,raw_text,processing_status) "
        "VALUES($1,$2,'txt','srs.txt',$3,$4,$5,$6::processing_status_enum)",
        sid, pid, f"{pid}/{sid}.txt", owner,
        SRS_TEXT if with_text else None, "completed" if with_text else "uploaded")
    return owner, pid, sid


async def request_scope(engine, owner, call):
    """Run `call(service)` the way get_db wraps one request."""
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(owner)})
        service = RequirementService(session)
        return await call(service)
    finally:
        if session.in_transaction():
            await session.rollback()          # what get_db does at request end
        await session.close()


async def test_text_extraction_is_persisted(admin, engine):
    owner, pid, sid = await seed(admin)

    async def call(svc):
        svc.storage = FakeStorage(SRS_TEXT.encode())
        return await svc.extract_source_text(owner, pid, sid)

    resp = await request_scope(engine, owner, call)
    assert resp.processing_status == "completed"

    row = await admin.fetchrow(
        "SELECT processing_status::text AS s, raw_text FROM requirement_sources WHERE id=$1", sid)
    assert row["s"] == "completed"
    assert row["raw_text"] and "lounge slot" in row["raw_text"]


async def test_failed_text_extraction_state_is_persisted(admin, engine):
    owner, pid, sid = await seed(admin)

    async def call(svc):
        svc.storage = FakeStorage(fail=True)
        with pytest.raises(HTTPException) as exc:
            await svc.extract_source_text(owner, pid, sid)
        assert exc.value.status_code == 500

    await request_scope(engine, owner, call)

    row = await admin.fetchrow(
        "SELECT processing_status::text AS s, extraction_error FROM requirement_sources WHERE id=$1", sid)
    assert row["s"] == "failed"
    assert "storage down" in row["extraction_error"]


async def test_requirement_extraction_is_persisted(admin, engine):
    owner, pid, sid = await seed(admin, with_text=True)

    async def call(svc):
        svc.extraction_strategy = FakeExtraction()
        return await svc.extract_requirements(owner, pid, sid)

    summary = await request_scope(engine, owner, call)
    assert summary.requirements_created == 2

    n = await admin.fetchval("SELECT count(*) FROM requirements WHERE project_id=$1", pid)
    v = await admin.fetchval(
        "SELECT count(*) FROM requirement_versions rv JOIN requirements r ON r.id=rv.requirement_id "
        "WHERE r.project_id=$1", pid)
    assert n == 2 and v == 2