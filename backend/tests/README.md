# Running the ReqIntel integration tests

These tests need a DISPOSABLE local PostgreSQL. They never touch Supabase.

1. Start a throw-away Postgres (Docker):

       docker run -d --name reqintel-testdb -p 5432:5432 -e POSTGRES_PASSWORD=testpw postgres:16

   (If port 5432 is taken, use `-p 5433:5432` and set `TEST_PG_PORT=5433` below.)

2. Install dev-only packages in your backend venv (not added to requirements.txt):

       pip install pytest pytest-asyncio httpx uvicorn

3. Build the test database from the SQL folder in your supabase_queries.zip
   (the folder that holds 01_extensions.sql ... 12_permissions.sql):

       cd backend
       python tests/setup_test_db.py "C:\path\to\supabase queries"

   Re-run it any time for a clean database. The script refuses to run unless
   the host is local and the database name contains "test".

4. Run everything:

       python -m pytest tests -v

Files
- test_project_deletion.py   Phase 1 permanent deletion (22 tests)
- test_project_persistence.py Phase 1.5 commit/persistence (22 tests; imports helpers
                              from test_project_deletion.py, so keep both together)
- persistence_app.py         test-only launcher used by the "restart the backend" test
- setup_test_db.py, db_setup/ builds the disposable database
