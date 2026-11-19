import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.services.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kvp")

IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_to_mongo()
        try:
            await ensure_indexes(get_database())
        except Exception:
            log.exception("Could not create indexes (is MongoDB reachable?)")
    except Exception:
        log.exception("Could not connect to MongoDB on startup")

    try:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    try:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    if settings.jwt_secret_key == "change-me-in-production" and settings.environment == "production":
        log.warning("JWT_SECRET_KEY is using default; set JWT_SECRET_KEY in production environment variables")

    # Background scheduler is disabled on serverless/Vercel functions
    task = None
    if settings.scheduler_enabled and not IS_SERVERLESS:
        task = asyncio.create_task(scheduler_loop(get_database))

    yield

    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await close_mongo_connection()


app = FastAPI(
    title=f"{settings.app_name} API",
    description="KVP Digital Field Management, AI & Impact Reporting System — Volunteer and Stakeholder API",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = settings.cors_origin_list
if not cors_origins or cors_origins == [""]:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins != ["*"] else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app" if cors_origins != ["*"] else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VercelPathNormalizer:
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            raw_matched = (
                headers.get(b"x-matched-path", b"")
                or headers.get(b"x-forwarded-uri", b"")
                or headers.get(b"x-original-uri", b"")
            ).decode("utf-8", "ignore")

            path = scope.get("path", "")
            matched = raw_matched.split("?")[0].strip()

            if matched and not matched.endswith(".py"):
                scope["path"] = matched
            elif path.startswith("/api/index.py"):
                sub = path[len("/api/index.py"):]
                scope["path"] = sub if sub.startswith("/") else ("/" + sub)
            elif path.startswith("/api/index"):
                sub = path[len("/api/index"):]
                scope["path"] = sub if sub.startswith("/") else ("/" + sub)

            if not scope.get("path"):
                scope["path"] = "/"

        await self.asgi_app(scope, receive, send)


class AISyncAfterWrite:
    """After a successful create/edit/delete, feed the change to the Ask AI index.

    Runs once the response has been sent and is capped in time; a failure never affects the request.
    The change stream catches every write since the last sync, so nothing is lost if one run is skipped.
    """

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SKIP = ("/ai/", "/auth/", "/push/", "/health")

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in self.WRITE_METHODS:
            await self.asgi_app(scope, receive, send)
            return
        status_code = 0

        async def capture(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.asgi_app(scope, receive, capture)
        path = scope.get("path", "")
        if status_code < 400 and settings.gemini_api_key.strip() and not any(s in path for s in self.SKIP):
            from app.services.ai_index import sync_changes
            try:
                await asyncio.wait_for(sync_changes(get_database(), budget=6.0), 8.0)
            except Exception:
                log.warning("AI index update after %s %s skipped", scope.get("method"), path, exc_info=True)


app.add_middleware(AISyncAfterWrite)
app.add_middleware(VercelPathNormalizer)

app.include_router(api_router, prefix=settings.api_v1_prefix)
if settings.api_v1_prefix != "/v1":
    app.include_router(api_router, prefix="/v1")


@app.api_route("/", methods=["GET", "HEAD"])  # HEAD for uptime / health probes
@app.get("/api")
@app.get("/api/")
@app.get("/api/index.py")
async def root():
    return {
        "status": "online",
        "message": f"{settings.app_name} API",
        "docs": "/docs",
        "health": "/health",
        "v1": settings.api_v1_prefix,
        "environment": settings.environment,
        "serverless": IS_SERVERLESS,
    }


@app.get("/health")
@app.get("/api/health")
@app.get("/api/v1/health")
@app.get("/v1/health")
async def health():
    db_status = "disconnected"
    db_error = None
    try:
        db = get_database()
        await db.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = "disconnected"
        db_error = str(e)

    return {
        "status": "ok",
        "app": settings.app_name,
        "database": db_status,
        "database_error": db_error,
        "serverless": IS_SERVERLESS,
    }


@app.get("/api/openapi.json", include_in_schema=False)
async def api_openapi():
    return app.openapi()

