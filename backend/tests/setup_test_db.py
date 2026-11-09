"""
Build the DISPOSABLE PostgreSQL database used by tests/test_project_*.py.

    python tests/setup_test_db.py "<folder containing 01_extensions.sql ... 12_permissions.sql>"

The folder is the one from your supabase_queries.zip (files 02..12 are used;
13/14 are not needed). Plus two small helper scripts in tests/db_setup/:
a stub of Supabase's auth/storage schemas and the live-database drift
(repository_versions, requirement_issue_waivers).

Connection (defaults suit `docker run -p 5432:5432 -e POSTGRES_PASSWORD=testpw postgres:16`):
    TEST_PG_HOST (127.0.0.1)  TEST_PG_PORT (5432)  TEST_PG_PASSWORD (testpw)
    TEST_PG_DB (reqintel_test)  TEST_PG_ADMIN_USER (postgres)

SAFETY: refuses to run unless the host is local and the database name contains
"test". It DROPS and recreates that database. It can never touch Supabase.
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

HOST = os.getenv("TEST_PG_HOST", "127.0.0.1")
PORT = int(os.getenv("TEST_PG_PORT", "5432"))
PW = os.getenv("TEST_PG_PASSWORD", "testpw")
DB = os.getenv("TEST_PG_DB", "reqintel_test")
ADMIN = os.getenv("TEST_PG_ADMIN_USER", "postgres")

HERE = Path(__file__).resolve().parent
SCHEMA_FILES = [
    "02_types.sql", "03_tables.sql", "04_constraints.sql", "05_indexes.sql",
    "06_functions.sql", "07_triggers.sql", "08_views.sql", "09_policies.sql",
    "10_storage.sql", "12_permissions.sql",
]


async def main(schema_dir: Path) -> None:
    if HOST not in ("127.0.0.1", "localhost", "::1") or "test" not in DB.lower():
        sys.exit(f"Refusing to run: host={HOST!r} db={DB!r}. Local host and a *test* database only.")

    for name in SCHEMA_FILES:
        if not (schema_dir / name).exists():
            sys.exit(f"Missing {name} in {schema_dir}")

    admin = await asyncpg.connect(user=ADMIN, password=PW, host=HOST, port=PORT, database="postgres")
    await admin.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    await admin.execute(f'CREATE DATABASE "{DB}"')
    await admin.close()

    conn = await asyncpg.connect(user=ADMIN, password=PW, host=HOST, port=PORT, database=DB)
    scripts = (
        [HERE / "db_setup" / "00_supabase_stub.sql"]
        + [schema_dir / n for n in SCHEMA_FILES]
        + [HERE / "db_setup" / "99_live_drift.sql"]
    )
    for path in scripts:
        print("applying", path.name)
        await conn.execute(path.read_text(encoding="utf-8"))
    await conn.execute(f"ALTER ROLE {ADMIN} PASSWORD '{PW}'")
    n = await conn.fetchval("SELECT count(*) FROM pg_policies WHERE schemaname='public'")
    print(f"done: database {DB!r} ready ({n} RLS policies)")
    await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1])))
