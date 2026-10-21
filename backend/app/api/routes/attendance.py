"""Attendance register and self-service NoteCam GPS Check-In / Check-Out."""
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.core.deps import CurrentUser, Db, Stakeholder
from app.core.permissions import Role
from app.db import collections as c
from app.services import audit
from app.utils.dates import today_local, utcnow
from app.utils.mongo import ObjectIdStr, oid, serialize

router = APIRouter(prefix="/attendance", tags=["attendance"])
AttendanceStatus = Literal["present", "absent", "late", "leave"]


class GpsCoordinates(BaseModel):
    lat: float
    lng: float
    accuracy_m: float | None = None
    captured_at: str | None = None
    village_name: str | None = None


class CheckInRequest(BaseModel):
    attendance_date: date | None = None
    check_in_time: str | None = None
    village_id: ObjectIdStr | None = None
    village_name: str | None = None
    gps: GpsCoordinates | None = None
    photo: str | None = Field(None, description="NoteCam photo with stamped GPS overlay (data URL or URL)")
    remarks: str | None = Field(None, max_length=1000)


class CheckOutRequest(BaseModel):
    attendance_date: date | None = None
    check_out_time: str | None = None
    village_id: ObjectIdStr | None = None
    village_name: str | None = None
    gps: GpsCoordinates | None = None
    photo: str | None = Field(None, description="NoteCam photo with stamped GPS overlay (data URL or URL)")
    remarks: str | None = Field(None, max_length=1000)


class AttendanceEntry(BaseModel):
    volunteer_id: ObjectIdStr
    attendance_date: date
    status: AttendanceStatus
    check_in: str | None = None
    check_out: str | None = None
    village_id: ObjectIdStr | None = None
    village_name: str | None = None
    check_in_photo: str | None = None
    check_out_photo: str | None = None
    check_in_gps: dict | None = None
    check_out_gps: dict | None = None
    remarks: str | None = Field(None, max_length=1000)


class AttendanceBatch(BaseModel):
    entries: list[AttendanceEntry] = Field(min_length=1, max_length=500)


@router.get("/today")
async def get_my_today_attendance(db: Db, user: CurrentUser):
    """Get the current user's (Tai or Admin) attendance status for today."""
    today = today_local()
    when = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    record = await db[c.VOLUNTEER_ATTENDANCE].find_one({"volunteer_id": user["_id"], "attendance_date": when})
    if not record:
        return {
            "attendance_date": today.isoformat(),
            "checked_in": False,
            "checked_out": False,
            "record": None,
        }
    return {
        "attendance_date": today.isoformat(),
        "checked_in": bool(record.get("check_in")),
        "checked_out": bool(record.get("check_out")),
        "record": serialize(record),
    }


@router.post("/check-in")
async def check_in(body: CheckInRequest, db: Db, user: CurrentUser):
    """Self-service check-in with NoteCam photo and GPS capture."""
    today = body.attendance_date or today_local()
    when = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    now = utcnow()
    check_in_str = body.check_in_time or now.strftime("%I:%M %p")

    # Determine village
    vid = oid(body.village_id) if body.village_id else (user.get("village_id") or (user.get("village_ids")[0] if user.get("village_ids") else None))
    v_name = body.village_name
    if not v_name and vid:
        vdoc = await db[c.VILLAGES].find_one({"_id": vid}, {"name": 1})
        if vdoc:
            v_name = vdoc.get("name")

    gps_dict = body.gps.model_dump() if body.gps else None
    if gps_dict and v_name and not gps_dict.get("village_name"):
        gps_dict["village_name"] = v_name

    update_fields = {
        "volunteer_id": user["_id"],
        "volunteer_name": user.get("name", ""),
        "role": user.get("role", "volunteer"),
        "village_id": vid,
        "village_name": v_name,
        "attendance_date": when,
        "status": "present",
        "check_in": check_in_str,
        "check_in_photo": body.photo,
        "check_in_gps": gps_dict,
        "updated_at": now,
        "updated_by": user["_id"],
    }
    if body.remarks:
        update_fields["remarks"] = body.remarks

    await db[c.VOLUNTEER_ATTENDANCE].update_one(
        {"volunteer_id": user["_id"], "attendance_date": when},
        {"$set": update_fields, "$setOnInsert": {"created_at": now, "created_by": user["_id"]}},
        upsert=True,
    )
    saved = await db[c.VOLUNTEER_ATTENDANCE].find_one({"volunteer_id": user["_id"], "attendance_date": when})
    await audit.log(db, user, "check_in", "attendance", saved["_id"], f"Check-in at {check_in_str} for {user.get('name')}")
    return serialize(saved)


@router.post("/check-out")
async def check_out(body: CheckOutRequest, db: Db, user: CurrentUser):
    """Self-service check-out with NoteCam photo and GPS capture."""
    today = body.attendance_date or today_local()
    when = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    now = utcnow()
    check_out_str = body.check_out_time or now.strftime("%I:%M %p")

    gps_dict = body.gps.model_dump() if body.gps else None
    v_name = body.village_name

    update_fields = {
        "check_out": check_out_str,
        "check_out_photo": body.photo,
        "check_out_gps": gps_dict,
        "updated_at": now,
        "updated_by": user["_id"],
    }
    if v_name:
        update_fields["village_name"] = v_name
    if body.village_id:
        update_fields["village_id"] = oid(body.village_id)
    if body.remarks:
        update_fields["checkout_remarks"] = body.remarks

    res = await db[c.VOLUNTEER_ATTENDANCE].update_one(
        {"volunteer_id": user["_id"], "attendance_date": when},
        {"$set": update_fields},
    )
    if res.matched_count == 0:
        # Check-out without prior check-in: create record with status present
        vid = oid(body.village_id) if body.village_id else (user.get("village_id") or (user.get("village_ids")[0] if user.get("village_ids") else None))
        doc = {
            "volunteer_id": user["_id"],
            "volunteer_name": user.get("name", ""),
            "role": user.get("role", "volunteer"),
            "village_id": vid,
            "village_name": v_name,
            "attendance_date": when,
            "status": "present",
            "check_in": None,
            "check_out": check_out_str,
            "check_out_photo": body.photo,
            "check_out_gps": gps_dict,
            "created_at": now,
            "created_by": user["_id"],
            "updated_at": now,
            "updated_by": user["_id"],
        }
        await db[c.VOLUNTEER_ATTENDANCE].insert_one(doc)

    saved = await db[c.VOLUNTEER_ATTENDANCE].find_one({"volunteer_id": user["_id"], "attendance_date": when})
    await audit.log(db, user, "check_out", "attendance", saved["_id"], f"Check-out at {check_out_str} for {user.get('name')}")
    return serialize(saved)


@router.get("")
async def list_attendance(
    db: Db,
    _: Stakeholder,
    start_date: date | None = None,
    end_date: date | None = None,
    volunteer_id: ObjectIdStr | None = None,
):
    query: dict = {}
    if start_date or end_date:
        query["attendance_date"] = {}
        if start_date:
            query["attendance_date"]["$gte"] = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        if end_date:
            query["attendance_date"]["$lte"] = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    if volunteer_id:
        query["volunteer_id"] = oid(volunteer_id)
    docs = await db[c.VOLUNTEER_ATTENDANCE].find(query).sort([("attendance_date", -1), ("volunteer_name", 1)]).limit(1000).to_list()
    return serialize(docs)


@router.post("/batch")
async def save_attendance(body: AttendanceBatch, db: Db, actor: Stakeholder):
    saved = []
    for entry in body.entries:
        volunteer = await db[c.USERS].find_one({"_id": oid(entry.volunteer_id)})
        if not volunteer:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"User {entry.volunteer_id} was not found")
        when = datetime.combine(entry.attendance_date, datetime.min.time(), tzinfo=timezone.utc)
        doc = {
            "volunteer_id": volunteer["_id"],
            "volunteer_name": volunteer.get("name", ""),
            "role": volunteer.get("role", "volunteer"),
            "village_id": oid(entry.village_id) if entry.village_id else volunteer.get("village_id"),
            "village_name": entry.village_name,
            "attendance_date": when,
            "status": entry.status,
            "check_in": entry.check_in,
            "check_out": entry.check_out,
            "remarks": entry.remarks,
            "updated_by": actor["_id"],
            "updated_at": utcnow(),
        }
        if entry.check_in_photo:
            doc["check_in_photo"] = entry.check_in_photo
        if entry.check_out_photo:
            doc["check_out_photo"] = entry.check_out_photo
        if entry.check_in_gps:
            doc["check_in_gps"] = entry.check_in_gps
        if entry.check_out_gps:
            doc["check_out_gps"] = entry.check_out_gps

        try:
            await db[c.VOLUNTEER_ATTENDANCE].update_one(
                {"volunteer_id": volunteer["_id"], "attendance_date": when},
                {"$set": doc, "$setOnInsert": {"created_at": utcnow(), "created_by": actor["_id"]}},
                upsert=True,
            )
        except DuplicateKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate attendance entry") from exc
        saved.append({"volunteer_id": entry.volunteer_id, "date": entry.attendance_date.isoformat(), "status": entry.status})
    await audit.log(db, actor, "upsert", "volunteer_attendance", None, f"Saved attendance for {len(saved)} entries")
    return {"saved": len(saved), "entries": saved}
