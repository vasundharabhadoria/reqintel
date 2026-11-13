"""
Report generation tests (Module 1, Phase 2).

API tests run against the DISPOSABLE PostgreSQL database described in
tests/README.md, once as the bypass-RLS role and once as the least-privilege
`reqintel_app` role. Supabase Storage is replaced by an in-memory fake, so
nothing here touches Supabase.

    cd backend
    python -m pytest tests/test_reports.py -v
"""

import io
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio

import test_project_deletion as base  # sets the dummy app environment first
from test_project_deletion import admin_conn, engine_for, seed_user  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from auth.schemas import UserResponse  # noqa: E402
from core.dependencies import get_current_user  # noqa: E402
from services import report_builder  # noqa: E402
from services.project_storage_cleanup import is_safe_object  # noqa: E402
from services.report_builder import build_report_data  # noqa: E402
from services.report_repository import ReportRepository  # noqa: E402

pytestmark = pytest.mark.asyncio

GOOD = dict(clarity="Good", completeness="Good", unambiguity="Good",
            consistency="Good", specificity="Good", testability="Good")

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "html": "text/html",
}


# ---------------------------------------------------------------------------
# Fakes and fixtures
# ---------------------------------------------------------------------------


class _Bucket:
    def __init__(self, owner):
        self.owner = owner

    def upload(self, path, content, options=None):
        if self.owner.fail_upload:
            raise Exception("boom: secret storage detail")
        self.owner.objects[path] = bytes(content)
        self.owner.content_types[path] = (options or {}).get("content-type")
        return {"path": path}

    def download(self, path):
        if self.owner.fail_download:
            raise Exception("boom: secret download detail")
        if path not in self.owner.objects:
            raise Exception("Object not found")
        return self.owner.objects[path]

    def remove(self, paths):
        if self.owner.fail_remove:
            raise Exception("storage down")
        for path in paths:
            self.owner.objects.pop(path, None)
        return [{"name": p} for p in paths]


class FakeReportsStorage:
    def __init__(self):
        self.storage = self
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str | None] = {}
        self.fail_upload = False
        self.fail_download = False
        self.fail_remove = False

    def from_(self, bucket):
        assert bucket == "reports", f"unexpected bucket {bucket!r}"
        return _Bucket(self)


@pytest.fixture
def storage(monkeypatch):
    fake = FakeReportsStorage()
    monkeypatch.setattr("core.storage.get_storage_client", lambda: fake)
    return fake


@pytest_asyncio.fixture
async def admin():
    conn = await admin_conn()
    # The reports DELETE policy lives in 15_permanent_delete.sql, which the
    # test-database builder does not apply. Create the same policy here.
    await conn.execute(
        "DROP POLICY IF EXISTS reports_delete_own_project ON reports;"
        "CREATE POLICY reports_delete_own_project ON reports "
        "FOR DELETE USING (fn_owns_project(project_id));"
    )
    yield conn
    await conn.close()


@pytest_asyncio.fixture(params=["postgres", "reqintel_app"])
async def client_for(request, admin, storage):
    """client_for(user_id) -> httpx client authenticated as that user."""

    engine = engine_for(request.param)

    from api.v1.dashboard import router as dashboard_router
    from api.v1.reports import router as reports_router
    from db.session import get_db

    clients = []

    def make(user_id, email="analyst@example.com"):
        app = FastAPI()
        app.include_router(reports_router)
        app.include_router(dashboard_router)

        async def current_user():
            return UserResponse(id=str(user_id), email=email, role="business_analyst")

        async def db_dep():
            session = AsyncSession(engine, expire_on_commit=False)
            await session.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(user_id)},
            )
            try:
                yield session
            finally:
                await session.rollback()
                await session.close()

        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_db] = db_dep
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        )
        clients.append(client)
        return client

    yield make

    for client in clients:
        await client.aclose()
    await engine.dispose()


async def seed_project(conn, owner, name="Telecom Billing", requirements=2):
    """Project with `requirements` requirements; REQ-001 is fully analysed."""

    pid, sid = uuid4(), uuid4()
    await conn.execute(
        "INSERT INTO projects(id,name,owner_id,project_type,description) "
        "VALUES($1,$2,$3,'Telecom','Billing modernisation')",
        pid, name, owner,
    )
    await conn.execute(
        "INSERT INTO requirement_sources(id,project_id,source_type,uploaded_by) "
        "VALUES($1,$2,'manual',$3)", sid, pid, owner,
    )

    ids = []
    for index in range(1, requirements + 1):
        rid = uuid4()
        await conn.execute(
            "INSERT INTO requirements(id,project_id,source_id,requirement_code,"
            "title,status,created_by) VALUES($1,$2,$3,$4,$5,'pending',$6)",
            rid, pid, sid, f"REQ-{index:03d}", f"Title {index}", owner,
        )
        vid = uuid4()
        await conn.execute(
            "INSERT INTO requirement_versions(id,requirement_id,version_number,"
            "requirement_text,created_by) VALUES($1,$2,1,$3,$4)",
            vid, rid, f"The system shall do thing {index}.", owner,
        )
        ids.append((rid, vid))

    if ids:
        analysis_id = uuid4()
        await conn.execute(
            "INSERT INTO ai_analysis(id,requirement_version_id,model_name,"
            "prompt_type,analysis_summary,recommendations,raw_response_json,"
            "ambiguity_detected) VALUES($1,$2,'m','requirement_quality_analysis',"
            "'Looks clear.',$3,$4::jsonb,FALSE)",
            analysis_id, ids[0][1], json.dumps(["Add a response time"]),
            json.dumps({"quality_assessment": GOOD}),
        )
        await conn.execute(
            "INSERT INTO ai_suggestions(ai_analysis_id,suggestion_text,"
            "suggestion_type) VALUES($1,'Specify the limit','clarity_improvement')",
            analysis_id,
        )

    return pid


async def generate(client, project_id, report_format="pdf"):
    return await client.post(
        "/api/v1/reports",
        json={"project_id": str(project_id), "report_format": report_format},
    )


async def count(conn, table, where="TRUE", *args):
    return await conn.fetchval(f"SELECT count(*) FROM {table} WHERE {where}", *args)


async def reports_of(conn, user_id):
    return await conn.fetchval(
        "SELECT count(*) FROM reports WHERE generated_by=$1", user_id
    )


async def logs_of(conn, user_id, action):
    return await conn.fetchval(
        "SELECT count(*) FROM activity_logs WHERE user_id=$1 AND action=$2",
        user_id, action,
    )


def pdf_text(content: bytes) -> str | None:
    pymupdf = pytest.importorskip("pymupdf")  # PyMuPDF is in requirements.txt
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return "\n".join(page.get_text() for page in document)


# ---------------------------------------------------------------------------
# Generation: all three formats, persistence, storage, activity log
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("report_format", ["pdf", "xlsx", "html"])
async def test_generate_persists_file_metadata_and_activity(
    admin, client_for, storage, report_format
):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)

    response = await generate(client_for(me), pid, report_format)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["project_id"] == str(pid)
    assert body["project_name"] == "Telecom Billing"
    assert body["generated_by"] == str(me)
    assert body["report_format"] == report_format
    assert body["file_name"].startswith("Telecom_Billing_report_")
    assert body["file_name"].endswith(f".{report_format}")
    assert "file_path" not in body  # storage path is never exposed

    # Stored file: path convention that project deletion cleanup relies on.
    path = f"{pid}/{body['id']}.{report_format}"
    assert list(storage.objects) == [path]
    assert is_safe_object(pid, "reports", path)
    assert storage.content_types[path] == CONTENT_TYPES[report_format]

    # Metadata row.
    row = await admin.fetchrow("SELECT * FROM reports WHERE id=$1", UUID(body["id"]))
    assert row["file_path"] == path
    assert str(row["report_format"]) == report_format
    assert row["generated_by"] == me and row["project_id"] == pid
    assert row["generated_at"] == datetime.fromisoformat(body["generated_at"])
    assert row["includes_ai_suggestions"] and row["includes_quality_scores"]
    # Sections that are NOT rendered must not be recorded as included.
    assert not row["includes_validation"] and not row["includes_change_impact"]

    # Activity log.
    log = await admin.fetchrow(
        "SELECT * FROM activity_logs WHERE entity_id=$1", UUID(body["id"])
    )
    assert log["action"] == "REPORT_GENERATED"
    assert log["user_id"] == me and log["entity_type"] == "report"
    details = json.loads(log["details"])
    assert details["project_name"] == "Telecom Billing"
    assert details["report_format"] == report_format
    assert details["project_id"] == str(pid)

    # The existing dashboard already understands this event.
    summary = (await client_for(me).get("/api/v1/dashboard/summary")).json()
    reported = [a for a in summary["recent_activity"] if a["action"] == "REPORT_GENERATED"]
    assert reported and reported[0]["detail"] == f"{report_format.upper()} report"
    assert reported[0]["project_name"] == "Telecom Billing"


async def test_report_content_is_real_data_only(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)  # REQ-001 analysed, REQ-002 NOT analysed
    client = client_for(me)

    xlsx = await generate(client, pid, "xlsx")
    workbook = load_workbook(io.BytesIO(storage.objects[f"{pid}/{xlsx.json()['id']}.xlsx"]))
    sheet = workbook["Requirements"]
    rows = {r[0].value: r for r in sheet.iter_rows(min_row=2)}

    assert rows["REQ-001"][7].value == 100            # six "Good" dimensions
    assert rows["REQ-002"][7].value == "Not analysed"  # nothing fabricated
    assert "thing 1" in rows["REQ-001"][5].value
    assert workbook["AI Suggestions"]["D2"].value == "Specify the limit"

    html_report = await generate(client, pid, "html")
    html = storage.objects[f"{pid}/{html_report.json()['id']}.html"].decode()
    assert "Telecom Billing" in html and "REQ-001" in html
    assert "Not analysed" in html and "Add a response time" in html

    pdf = await generate(client, pid, "pdf")
    assert storage.objects[f"{pid}/{pdf.json()['id']}.pdf"].startswith(b"%PDF-")
    extracted = pdf_text(storage.objects[f"{pid}/{pdf.json()['id']}.pdf"])
    assert "REQ-001" in extracted and "Not analysed" in extracted


async def test_project_without_requirements_still_reports(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me, requirements=0)

    for fmt in ("pdf", "xlsx", "html"):
        response = await generate(client_for(me), pid, fmt)
        assert response.status_code == 201, response.text

    html = [v for k, v in storage.objects.items() if k.endswith(".html")][0].decode()
    assert "no requirements yet" in html


# ---------------------------------------------------------------------------
# Ownership / authorisation
# ---------------------------------------------------------------------------


async def test_cannot_generate_for_another_users_or_unknown_project(
    admin, client_for, storage
):
    me, other = await seed_user(admin), await seed_user(admin)
    others_project = await seed_project(admin, other)

    for project_id in (others_project, uuid4()):
        response = await generate(client_for(me), project_id)
        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found."

    assert storage.objects == {}
    assert await reports_of(admin, me) == 0
    assert await logs_of(admin, me, "REPORT_GENERATED") == 0


async def test_invalid_input_is_rejected(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)
    client = client_for(me)

    assert (await client.post("/api/v1/reports", json={"project_id": "nope", "report_format": "pdf"})).status_code == 422
    assert (await generate(client, pid, "docx")).status_code == 422
    assert (await client.post("/api/v1/reports", json={"report_format": "pdf"})).status_code == 422
    assert (await client.get("/api/v1/reports/not-a-uuid")).status_code == 422
    assert storage.objects == {} and await reports_of(admin, me) == 0


async def test_other_users_cannot_view_list_download_or_delete(
    admin, client_for, storage
):
    me, other = await seed_user(admin), await seed_user(admin)
    pid = await seed_project(admin, me)
    report_id = (await generate(client_for(me), pid, "pdf")).json()["id"]

    intruder = client_for(other)
    assert (await intruder.get(f"/api/v1/reports/{report_id}")).status_code == 404
    assert (await intruder.get(f"/api/v1/reports/{report_id}/download")).status_code == 404
    assert (await intruder.delete(f"/api/v1/reports/{report_id}")).status_code == 404

    listing = (await intruder.get("/api/v1/reports")).json()
    assert listing == {"total": 0, "items": []}
    listing = (await intruder.get("/api/v1/reports", params={"project_id": str(pid)})).json()
    assert listing["total"] == 0  # the project id is not trusted

    # The owner's report, file and log are untouched.
    assert await count(admin, "reports", "id=$1", UUID(report_id)) == 1
    assert len(storage.objects) == 1
    assert await logs_of(admin, me, "REPORT_DELETED") == 0
    assert await logs_of(admin, other, "REPORT_DELETED") == 0


async def test_every_endpoint_requires_authentication():
    from api.v1.reports import router

    app = FastAPI()
    app.include_router(router)
    rid = uuid4()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        calls = [
            client.post("/api/v1/reports", json={"project_id": str(uuid4()), "report_format": "pdf"}),
            client.get("/api/v1/reports"),
            client.get(f"/api/v1/reports/{rid}"),
            client.get(f"/api/v1/reports/{rid}/download"),
            client.delete(f"/api/v1/reports/{rid}"),
        ]
        for call in calls:
            assert (await call).status_code == 401


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


async def test_storage_failure_creates_no_row_and_no_activity(
    admin, client_for, storage
):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)
    storage.fail_upload = True

    response = await generate(client_for(me), pid)

    assert response.status_code == 500
    assert "secret" not in response.text and "boom" not in response.text
    assert await reports_of(admin, me) == 0
    assert await logs_of(admin, me, "REPORT_GENERATED") == 0
    assert storage.objects == {}


async def test_builder_failure_stores_and_logs_nothing(
    admin, client_for, storage, monkeypatch
):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)

    def explode(_data):
        raise RuntimeError("internal render detail")

    monkeypatch.setitem(report_builder.FORMAT_INFO["pdf"], "builder", explode)

    response = await generate(client_for(me), pid, "pdf")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to generate the PDF report."
    assert "internal render detail" not in response.text
    assert storage.objects == {}
    assert await reports_of(admin, me) == 0
    assert await logs_of(admin, me, "REPORT_GENERATED") == 0


@pytest.mark.parametrize("failing", ["insert_report", "log_activity"])
async def test_database_failure_removes_uploaded_file_and_rolls_back(
    admin, client_for, storage, monkeypatch, failing
):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)

    async def explode(*_args, **_kwargs):
        raise RuntimeError("db exploded: internal detail")

    monkeypatch.setattr(ReportRepository, failing, explode)

    response = await generate(client_for(me), pid)

    assert response.status_code == 500
    assert "internal detail" not in response.text
    assert storage.objects == {}                      # orphan removed
    assert await reports_of(admin, me) == 0           # nothing committed
    assert await logs_of(admin, me, "REPORT_GENERATED") == 0


async def test_orphan_cleanup_failure_still_returns_clean_error(
    admin, client_for, storage, monkeypatch
):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)

    async def explode(*_args, **_kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(ReportRepository, "insert_report", explode)
    storage.fail_remove = True

    response = await generate(client_for(me), pid)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to save the report. Please try again."
    assert await reports_of(admin, me) == 0


# ---------------------------------------------------------------------------
# List / metadata / download / delete
# ---------------------------------------------------------------------------


async def test_list_is_newest_first_and_filterable(admin, client_for, storage):
    me = await seed_user(admin)
    p1 = await seed_project(admin, me, "Alpha")
    p2 = await seed_project(admin, me, "Beta")
    client = client_for(me)

    first = (await generate(client, p1, "pdf")).json()["id"]
    second = (await generate(client, p2, "xlsx")).json()["id"]
    third = (await generate(client, p1, "html")).json()["id"]

    everything = (await client.get("/api/v1/reports")).json()
    assert everything["total"] == 3
    assert [r["id"] for r in everything["items"]] == [third, second, first]

    only_p1 = (await client.get("/api/v1/reports", params={"project_id": str(p1)})).json()
    assert {r["id"] for r in only_p1["items"]} == {first, third}

    only_xlsx = (await client.get("/api/v1/reports", params={"report_format": "xlsx"})).json()
    assert [r["id"] for r in only_xlsx["items"]] == [second]

    one = (await client.get(f"/api/v1/reports/{second}")).json()
    assert one["project_name"] == "Beta" and one["report_format"] == "xlsx"


async def test_download_returns_exact_stored_bytes_safely(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)
    client = client_for(me)

    body = (await generate(client, pid, "html")).json()
    response = await client.get(f"/api/v1/reports/{body['id']}/download")

    assert response.status_code == 200
    assert response.content == storage.objects[f"{pid}/{body['id']}.html"]
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{body["file_name"]}"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_download_failures_are_clean(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)
    client = client_for(me)
    body = (await generate(client, pid, "pdf")).json()
    url = f"/api/v1/reports/{body['id']}/download"

    storage.fail_download = True
    response = await client.get(url)
    assert response.status_code == 500 and "secret" not in response.text
    storage.fail_download = False

    storage.objects.clear()  # the stored file vanished
    response = await client.get(url)
    assert response.status_code == 404

    # A row with no stored path (reports are append-only, so insert one) is
    # reported as unavailable, not a crash.
    no_path_id = uuid4()
    await admin.execute(
        "INSERT INTO reports(id,project_id,generated_by,report_format,file_path) "
        "VALUES($1,$2,$3,'pdf',NULL)", no_path_id, pid, me,
    )
    assert (await client.get(f"/api/v1/reports/{no_path_id}/download")).status_code == 404


async def test_delete_removes_row_file_and_logs(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)
    client = client_for(me)
    report_id = (await generate(client, pid)).json()["id"]

    response = await client.delete(f"/api/v1/reports/{report_id}")

    assert response.status_code == 204
    assert await count(admin, "reports", "id=$1", UUID(report_id)) == 0
    assert storage.objects == {}
    log = await admin.fetchrow(
        "SELECT * FROM activity_logs WHERE action='REPORT_DELETED' AND entity_id=$1",
        UUID(report_id),
    )
    assert log is not None and log["user_id"] == me
    assert (await client.delete(f"/api/v1/reports/{report_id}")).status_code == 404


async def test_delete_succeeds_even_if_file_cleanup_fails(admin, client_for, storage):
    me = await seed_user(admin)
    pid = await seed_project(admin, me)
    client = client_for(me)
    report_id = (await generate(client, pid)).json()["id"]
    storage.fail_remove = True

    response = await client.delete(f"/api/v1/reports/{report_id}")

    assert response.status_code == 204                      # row is gone
    assert await count(admin, "reports", "id=$1", UUID(report_id)) == 0
    assert len(storage.objects) == 1                        # logged orphan


# ---------------------------------------------------------------------------
# Builders in isolation (no database)
# ---------------------------------------------------------------------------


def _hostile_data():
    now = datetime.now(timezone.utc)
    project = dict(
        name='Evil <b>&</b> "Name"', client_name=None, project_type=None,
        description="=cmd|' /C calc'!A0\nline \x0c two", status="active",
        created_at=now, updated_at=now,
    )
    rows = [dict(
        id=uuid4(), requirement_code="REQ-001", title='=HYPERLINK("http://x")',
        status="pending", created_at=now, updated_at=now, version_number=1,
        version_count=1, requirement_text="<script>alert(1)</script> \x0c 日本語",
        change_summary=None, ai_analysis_id=None, model_name=None,
        analysis_summary=None, recommendations=None, ambiguity_detected=None,
        analysed_at=None, quality_assessment=None,
    )]
    return build_report_data(project, rows, [], now, "a@b.c")


async def test_builders_neutralise_hostile_text():
    data = _hostile_data()

    html = report_builder.build_html(data).decode()
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<b>&</b>" not in html

    sheet = load_workbook(io.BytesIO(report_builder.build_xlsx(data)))["Requirements"]
    assert sheet["B2"].value == '=HYPERLINK("http://x")'
    assert sheet["B2"].data_type == "s"       # text, never a formula
    assert "\x0c" not in sheet["F2"].value    # control char stripped

    assert report_builder.build_pdf(data).startswith(b"%PDF-")


async def test_missing_analysis_yields_no_score():
    data = _hostile_data()
    item = data.requirements[0]

    assert item.quality_score is None and item.quality_labels == {}
    assert data.average_quality is None