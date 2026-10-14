"""Stakeholder-managed volunteer attendance register."""
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.core.deps import Db, Stakeholder
from app.core.permissions import Role
from app.db import collections as c
from app.services import audit
from app.utils.dates import utcnow
from app.utils.mongo import ObjectIdStr, oid, serialize

router = APIRouter(prefix="/attendance", tags=["volunteer attendance"])
AttendanceStatus = Literal["present", "absent", "late", "leave"]

class AttendanceEntry(BaseModel):
    volunteer_id: ObjectIdStr
    attendance_date: date
    status: AttendanceStatus
    check_in: str | None = None
    check_out: str | None = None
    remarks: str | None = Field(None, max_length=1000)

class AttendanceBatch(BaseModel):
    entries: list[AttendanceEntry] = Field(min_length=1, max_length=500)

@router.get("")
async def list_attendance(db: Db, _: Stakeholder, start_date: date | None = None, end_date: date | None = None, volunteer_id: ObjectIdStr | None = None):
    query: dict = {}
    if start_date or end_date:
        query["attendance_date"] = {}
        if start_date: query["attendance_date"]["$gte"] = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        if end_date: query["attendance_date"]["$lte"] = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    if volunteer_id: query["volunteer_id"] = oid(volunteer_id)
    docs = await db[c.VOLUNTEER_ATTENDANCE].find(query).sort([("attendance_date", -1), ("volunteer_name", 1)]).limit(1000).to_list()
    return serialize(docs)

@router.post("/batch")
async def save_attendance(body: AttendanceBatch, db: Db, actor: Stakeholder):
    saved = []
    for entry in body.entries:
        volunteer = await db[c.USERS].find_one({"_id": oid(entry.volunteer_id), "role": Role.VOLUNTEER.value})
        if not volunteer:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Volunteer {entry.volunteer_id} was not found")
        when = datetime.combine(entry.attendance_date, datetime.min.time(), tzinfo=timezone.utc)
        doc = {"volunteer_id": volunteer["_id"], "volunteer_name": volunteer.get("name", ""), "village_id": volunteer.get("village_id"),
               "attendance_date": when, "status": entry.status, "check_in": entry.check_in, "check_out": entry.check_out,
               "remarks": entry.remarks, "updated_by": actor["_id"], "updated_at": utcnow()}
        try:
            await db[c.VOLUNTEER_ATTENDANCE].update_one({"volunteer_id": volunteer["_id"], "attendance_date": when},
                {"$set": doc, "$setOnInsert": {"created_at": utcnow(), "created_by": actor["_id"]}}, upsert=True)
        except DuplicateKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate attendance entry") from exc
        saved.append({"volunteer_id": entry.volunteer_id, "date": entry.attendance_date.isoformat(), "status": entry.status})
    await audit.log(db, actor, "upsert", "volunteer_attendance", None, f"Saved attendance for {len(saved)} volunteer entries")
    return {"saved": len(saved), "entries": saved}
