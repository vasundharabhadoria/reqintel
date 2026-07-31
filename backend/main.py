from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.auth import router as auth_router


app = FastAPI(
    title="ReqIntel API",
    description="AI-Powered Enterprise Requirement Intelligence Platform",
    version="1.0.0",
)

# Allow the React frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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