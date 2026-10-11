"""Device-facing delivery: Web Push subscriptions, SMS outbox, offline sync status (PRD 4.15, 4.17)."""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from app.core.config import settings
from app.core.deps import CurrentUser, Db, Pagination, Stakeholder
from app.db import collections as c
from app.services import audit, notifications, push
from app.services.messaging import send_sms
from app.utils.dates import utcnow
from app.utils.mongo import paginate, serialize

router = APIRouter(tags=["push, messaging & sync"])


# ---------------------------------------------------------------- Web Push

class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str = Field(pattern=r"^https://")
    keys: PushKeys
    user_agent: str | None = None


@router.get("/push/public-key")
async def push_public_key(_: CurrentUser):
    """VAPID public key for the PWA's PushManager.subscribe()."""
    if not settings.push_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web Push is not configured on the server")
    return {"public_key": settings.vapid_public_key}


@router.post("/push/subscriptions", status_code=status.HTTP_201_CREATED)
async def subscribe(body: PushSubscription, db: Db, user: CurrentUser):
    now = utcnow()
    await db[c.PUSH_SUBSCRIPTIONS].update_one(
        {"endpoint": body.endpoint},
        {"$set": {"user_id": user["_id"], "keys": body.keys.model_dump(), "user_agent": body.user_agent, "updated_at": now},
         "$setOnInsert": {"created_at": now, "last_success_at": None}},
        upsert=True,
    )
    return {"subscribed": True, "devices": await db[c.PUSH_SUBSCRIPTIONS].count_documents({"user_id": user["_id"]})}


@router.delete("/push/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(db: Db, user: CurrentUser, endpoint: str):
    await db[c.PUSH_SUBSCRIPTIONS].delete_one({"endpoint": endpoint, "user_id": user["_id"]})


@router.post("/push/test")
async def push_test(db: Db, user: CurrentUser):
    """Send a test push to all of the caller's devices."""
    if not settings.push_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web Push is not configured on the server")
    sent = await push.send_to_user(db, user["_id"], {"type": "test", "title": "Test notification",
                                                      "body": "Push notifications are working."})
    return {"delivered_to_devices": sent}


# ---------------------------------------------------------------- SMS outbox

class TestSms(BaseModel):
    to: str = Field(pattern=r"^(\+?91)?[6-9]\d{9}$")
    body: str = Field(min_length=1, max_length=500)


@router.get("/messages")
async def outbox(db: Db, _: Stakeholder, pg: Pagination, status_: str | None = Query(None, alias="status"),
                 purpose: str | None = None):
    query: dict = {}
    if status_:
        query["status"] = status_
    if purpose:
        query["purpose"] = purpose
    page = await paginate(db[c.MESSAGE_OUTBOX], query, pg.page, pg.page_size, sort=[("created_at", -1)])
    page["by_status"] = {d["_id"]: d["n"] async for d in await db[c.MESSAGE_OUTBOX].aggregate(
        [{"$match": query}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    return page


@router.post("/messages/test-sms")
async def test_sms(body: TestSms, db: Db, actor: Stakeholder):
    """Send one SMS through the active provider to check the configuration."""
    doc = await send_sms(db, body.to, body.body, purpose="test", created_by=actor["_id"])
    await audit.log(db, actor, "create", "message", doc["_id"], f"Test SMS ({doc['status']})")
    return serialize(doc)


# ---------------------------------------------------------------- offline sync status

class SyncReport(BaseModel):
    device_id: str = Field(min_length=3, max_length=100)
    pending: int = Field(0, ge=0, description="Records saved offline, not yet uploaded")
    failed: int = Field(0, ge=0, description="Records that failed to upload")
    synced_in_batch: int = Field(0, ge=0, description="Records uploaded since the previous report")
    last_synced_at: datetime | None = None
    app_version: str | None = None
    errors: list[str] = Field(default_factory=list, max_length=20)


SyncState = Literal["synced", "pending", "failed"]


def _state(report: SyncReport) -> SyncState:
    return "failed" if report.failed else ("pending" if report.pending else "synced")


@router.post("/sync/status")
async def report_sync_status(body: SyncReport, db: Db, user: CurrentUser):
    """Called by the PWA after each sync attempt. Notifies the user when records fail or recover."""
    now = utcnow()
    state = _state(body)
    before = await db[c.SYNC_STATUS].find_one_and_update(
        {"user_id": user["_id"], "device_id": body.device_id},
        {"$set": {**body.model_dump(), "state": state, "last_report_at": now},
         "$setOnInsert": {"first_seen_at": now}},
        upsert=True, return_document=ReturnDocument.BEFORE,
    )
    previous = (before or {}).get("state")
    if state == "failed" and previous != "failed":
        await notifications.notify(db, user["_id"], "sync_failed", f"{body.failed} record(s) failed to sync",
                                   (body.errors or ["Open the app while online to retry."])[0], severity="high",
                                   dedupe_key=f"sync_failed:{body.device_id}:{now:%Y%m%d}")
    elif state == "synced" and previous in ("failed", "pending") and body.synced_in_batch:
        await notifications.notify(db, user["_id"], "sync_complete", "All records synced",
                                   f"{body.synced_in_batch} record(s) uploaded.", severity="info")
    return {"state": state, "previous_state": previous}


@router.get("/sync/status")
async def sync_overview(db: Db, _: Stakeholder, stale_after_hours: int = 48):
    """Per-device sync state for all users, flagging devices with failures or no recent sync."""
    cutoff = utcnow() - timedelta(hours=stale_after_hours)
    users = {u["_id"]: u async for u in db[c.USERS].find({}, {"name": 1, "role": 1, "village_id": 1})}
    rows = []
    async for s in db[c.SYNC_STATUS].find().sort("last_report_at", -1):
        u = users.get(s["user_id"], {})
        rows.append({**serialize(s), "user_name": u.get("name"), "role": u.get("role"),
                     "stale": s["last_report_at"] < cutoff})
    return {
        "devices": rows,
        "counts": {
            "failed": sum(1 for r in rows if r["state"] == "failed"),
            "pending": sum(1 for r in rows if r["state"] == "pending"),
            "stale": sum(1 for r in rows if r["stale"]),
            "total": len(rows),
        },
    }
