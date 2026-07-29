from fastapi import FastAPI

from api.v1.auth import router as auth_router


app = FastAPI(
    title="ReqIntel API",
    description="AI-Powered Enterprise Requirement Intelligence Platform",
    version="1.0.0",
)

app.include_router(auth_router)


@app.get(
    "/",
    tags=["Health"],
)
def root() -> dict[str, str]:
    """Basic API health endpoint."""

    return {
        "message": "ReqIntel Backend Running",
    }