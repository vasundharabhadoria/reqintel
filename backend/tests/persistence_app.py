"""
Test-only launcher used by tests/test_project_persistence.py to RESTART a real
backend process. It mounts the REAL projects router and the REAL
db.session.get_db / ProjectService / ProjectRepository. The only thing
replaced is get_current_user, because the real one calls Supabase Auth over
the network; here the user id comes from an X-Test-User header.
"""

from fastapi import FastAPI, Header

from api.v1.projects import router
from auth.schemas import UserResponse
from core.dependencies import get_current_user

app = FastAPI()
app.include_router(router)


def _test_user(x_test_user: str = Header(...)) -> UserResponse:
    return UserResponse(id=x_test_user, email="t@example.com", role="business_analyst")


app.dependency_overrides[get_current_user] = _test_user
