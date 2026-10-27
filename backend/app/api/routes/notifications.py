"""In-app notifications and Stakeholder announcements (PRD 4.15)."""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, Db, Pagination, Stakeholder
from app.core.permissions import Role
from app.db import collections as c
from app.services import audit, notifications
from app.services.scheduler import run_jobs_once
from app.utils.dates import utcnow
from app.utils.mongo import ObjectIdStr, get_or_404, oid, oids, paginate

router = APIRouter(prefix="/notifications", tags=["notifications"])


class Announcement(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=1, max_length=2000)
    audience: Literal["all_volunteers", "all_stakeholders", "everyone", "users", "village"] = "all_volunteers"
    user_ids: list[ObjectIdStr] = Field(default_factory=list)
    village_id: ObjectIdStr | None = None
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"


@router.get("")
async def my_notifications(db: Db, user: CurrentUser, pg: Pagination, unread_only: bool = False, type: str | None = None):
    query: dict = {"user_id": user["_id"]}
    if unread_only:
        query["is_read"] = False
    if type:
        query["type"] = type
    page = await paginate(db[c.NOTIFICATIONS], query, pg.page, pg.page_size, sort=[("created_at", -1)])
    page["unread"] = await db[c.NOTIFICATIONS].count_documents({"user_id": user["_id"], "is_read": False})
    return page


@router.get("/unread-count")
async def unread_count(db: Db, user: CurrentUser):
    return {"unread": await db[c.NOTIFICATIONS].count_documents({"user_id": user["_id"], "is_read": False})}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, db: Db, user: CurrentUser):
    n = await get_or_404(db[c.NOTIFICATIONS], notification_id, "Notification", {"user_id": user["_id"]})
    await db[c.NOTIFICATIONS].update_one({"_id": n["_id"]}, {"$set": {"is_read": True, "read_at": utcnow()}})
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(db: Db, user: CurrentUser):
    res = await db[c.NOTIFICATIONS].update_many({"user_id": user["_id"], "is_read": False},
                                                {"$set": {"is_read": True, "read_at": utcnow()}})
    return {"updated": res.modified_count}


@router.post("/announce", status_code=status.HTTP_201_CREATED)
async def announce(body: Announcement, db: Db, actor: Stakeholder):
    """Send an in-app message (e.g. a job/assignment instruction) to volunteers or other users."""
    from app.core.deps import check_not_read_only
    check_not_read_only(actor)
    query: dict = {"is_active": True}
    if body.audience == "all_volunteers":
        query["role"] = Role.VOLUNTEER.value
    elif body.audience == "all_stakeholders":
        query["role"] = {"$in": [Role.SUPER_ADMIN.value, Role.ADMIN_1.value, Role.ADMIN_2.value, "super_admin", "admin_1", "admin_2", "admin", "stakeholder"]}
    elif body.audience == "users":
        if not body.user_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "user_ids is required for audience 'users'")
        query["_id"] = {"$in": oids(body.user_ids)}
    elif body.audience == "village":
        if not body.village_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "village_id is required for audience 'village'")
        query["village_ids"] = oid(body.village_id)
    sent = 0
    async for u in db[c.USERS].find(query, {"_id": 1}):
        if await notifications.notify(db, u["_id"], "announcement", body.title, body.message, severity=body.severity):
            sent += 1
    await audit.log(db, actor, "create", "announcement", None, f"Announcement '{body.title}' to {body.audience}",
                    meta={"recipients": sent})
    return {"sent": sent}


@router.post("/run-checks")
async def run_checks_now(db: Db, _: Stakeholder):
    """Run the reminder/alert/escalation jobs immediately (normally run by the background scheduler)."""
    return await run_jobs_once(db)
