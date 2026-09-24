import truststore
truststore.inject_into_ssl()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.auth import router as auth_router
from api.v1.projects import router as projects_router
from api.v1.requirements import router as requirements_router
from master_module.routes import router as master_module_router


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
app.include_router(projects_router)
app.include_router(requirements_router)
app.include_router(master_module_router)


@app.get(
    "/",
    tags=["Health"],
)
def root() -> dict[str, str]:
    """Basic API health endpoint."""

    return {
        "message": "ReqIntel Backend Running",
    }