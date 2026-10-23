import asyncio
import contextlib
import logging
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    try:
        await ensure_indexes(get_database())
    except Exception:
        log.exception("Could not create indexes (is MongoDB reachable?)")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    if settings.jwt_secret_key == "change-me-in-production" and settings.environment != "development":
        raise RuntimeError("Set JWT_SECRET_KEY before running outside development")

    task = asyncio.create_task(scheduler_loop(get_database)) if settings.scheduler_enabled else None
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.api_route("/", methods=["GET", "HEAD"])  # HEAD for uptime / health probes
async def root():
    return {"message": f"{settings.app_name} API", "docs": "/docs"}
