import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import admin, auth, expenditures, projects, repository, reports, risks, tasks
from .core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables (and the initial admin) exist before serving traffic.
    # Makes the app deployable on hosts without shell access (e.g. Render free).
    from .core.bootstrap import bootstrap_db

    try:
        bootstrap_db()
    except Exception:
        logger.exception("Database bootstrap failed on startup")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    description="3CORE Portal - Decoupled Architecture",
    lifespan=lifespan,
)

# CORS — explicit origin list only when credentials are enabled.
# Refuse to combine wildcard + credentials (browsers reject it; also a CSRF risk).
allow_credentials = True
allow_origins = settings.CORS_ORIGINS
if "*" in allow_origins:
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Return the 500 *through* the middleware stack so CORS headers are still
    # attached. Without this, an unhandled error reaches Starlette's outermost
    # error middleware and the browser misreports it as a CORS failure.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(risks.router, prefix="/risks", tags=["Risks"])
app.include_router(expenditures.router, prefix="/expenditures", tags=["Expenditures"])
app.include_router(repository.router, prefix="/repository", tags=["Repository"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])


@app.get("/health")
def health_check():
    return {"status": "operational", "version": "2.0.0"}
