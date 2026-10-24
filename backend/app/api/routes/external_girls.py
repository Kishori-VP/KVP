"""External girls and phone outreach calls.

External girls are girls outside the regular village Kishori groups.
Their data is visible to all users (both Stakeholders and Tais/Volunteers),
and Tais reach and support them via phone calls instead of house visits.
"""

from datetime import date, timedelta
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import CurrentUser, Db, Pagination
from app.db import collections as c
from app.schemas.external_girls import (
    CallPurpose,
    CallStatus,
    ExternalCallCreate,
    ExternalCallUpdate,
    ExternalGirlCreate,
    ExternalGirlUpdate,
)
from app.services import audit
from app.utils.dates import day_range, to_dt, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, paginate, serialize
from app.utils.translit import to_latin

router = APIRouter(tags=["external girls"])


# ---------------------------------------------------------------- External Girls


@router.get("/external-girls")
async def list_external_girls(
    db: Db,
    user: CurrentUser,
    pg: Pagination,
    q: str | None = Query(None, description="Search by name, phone, location or guardian"),
    status: Literal["active", "follow_up", "closed"] | None = None,
    eligible_for_call: bool = Query(
        False, description="Filter for girls not called in the last 30 days"
    ),
):
    """List external girls. Visible to all users without village scoping."""
    query: dict = {"is_deleted": {"$ne": True}}
    if status:
        query["status"] = status
    if eligible_for_call:
        one_month_ago = utcnow() - timedelta(days=30)
        query["$or"] = [
            {"call_summary.last_call_at": None},
            {"call_summary.last_call_at": {"$lt": one_month_ago}},
            {"call_summary.last_call_at": {"$exists": False}},
        ]
    if q:
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        q_or = [
            {"name": rx},
            {"name_en": rx},
            {"phone": rx},
            {"alt_phone": rx},
            {"location": rx},
            {"guardian_name": rx},
            {"school_or_college": rx},
            {"transferred_from_girl_code": rx},
            {"transfer_reason": rx},
        ]
        if "$or" in query:
            query["$and"] = [{"$or": query.pop("$or")}, {"$or": q_or}]
        else:
            query["$or"] = q_or

    sort = [("updated_at", -1)]
    result = await paginate(db[c.EXTERNAL_GIRLS], query, pg.page, pg.page_size, sort=sort)
    return result


@router.post("/external-girls", status_code=status.HTTP_201_CREATED)
async def create_external_girl(
    body: ExternalGirlCreate,
    db: Db,
    user: CurrentUser,
):
    """Register a new external girl. Available to all users."""
    now = utcnow()
    data = body.model_dump()
    if not data.get("name_en") and data.get("name"):
        data["name_en"] = to_latin(data["name"])

    doc = {
        **data,
        "dob": to_dt(data["dob"]) if data.get("dob") else None,
        "call_summary": {
            "total_calls": 0,
            "last_call_at": None,
            "last_call_status": None,
            "last_caller_name": None,
        },
        "is_deleted": False,
        "created_by": user["_id"],
        "created_by_name": user.get("name") or user.get("username"),
        "created_at": now,
        "updated_at": now,
    }
    res = await db[c.EXTERNAL_GIRLS].insert_one(doc)
    await audit.log(
        db,
        user,
        "create",
        "external_girl",
        res.inserted_id,
        f"Registered external girl {doc['name']}",
    )
    return serialize(doc)


@router.get("/external-girls/{girl_id}")
async def get_external_girl(
    girl_id: str,
    db: Db,
    user: CurrentUser,
):
    """Get single external girl with recent calls."""
    girl = await get_or_404(db[c.EXTERNAL_GIRLS], girl_id, "External girl")
    out = serialize(girl)
    calls = await db[c.EXTERNAL_CALLS].find(
        {"external_girl_id": girl["_id"]}
    ).sort("call_date", -1).limit(15).to_list()
    out["recent_calls"] = serialize(calls)
    return out


@router.patch("/external-girls/{girl_id}")
async def update_external_girl(
    girl_id: str,
    body: ExternalGirlUpdate,
    db: Db,
    user: CurrentUser,
):
    """Update external girl profile."""
    before = await get_or_404(db[c.EXTERNAL_GIRLS], girl_id, "External girl")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return serialize(before)

    if "dob" in updates:
        updates["dob"] = to_dt(updates["dob"]) if updates["dob"] else None
    if "name" in updates and not updates.get("name_en"):
        updates["name_en"] = to_latin(updates["name"])

    updates["updated_at"] = utcnow()
    await db[c.EXTERNAL_GIRLS].update_one({"_id": before["_id"]}, {"$set": updates})
    after = await db[c.EXTERNAL_GIRLS].find_one({"_id": before["_id"]})
    await audit.log(
        db,
        user,
        "update",
        "external_girl",
        before["_id"],
        f"Updated external girl {after.get('name')}",
        diff(before, after),
    )
    return serialize(after)


@router.delete("/external-girls/{girl_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_external_girl(
    girl_id: str,
    db: Db,
    user: CurrentUser,
    reason: str = Query("Deleted", min_length=2),
):
    """Soft delete an external girl."""
    girl = await get_or_404(db[c.EXTERNAL_GIRLS], girl_id, "External girl")
    now = utcnow()
    await db[c.EXTERNAL_GIRLS].update_one(
        {"_id": girl["_id"]},
        {"$set": {"is_deleted": True, "deleted_at": now, "delete_reason": reason}},
    )
    await audit.log(
        db,
        user,
        "delete",
        "external_girl",
        girl["_id"],
        f"Deleted external girl {girl.get('name')}: {reason}",
    )


# ---------------------------------------------------------------- External Calls


@router.get("/external-calls")
async def list_external_calls(
    db: Db,
    user: CurrentUser,
    pg: Pagination,
    external_girl_id: ObjectIdStr | None = None,
    caller_id: ObjectIdStr | None = None,
    status_: Annotated[CallStatus | None, Query(alias="status")] = None,
    purpose: CallPurpose | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """List calls made to external girls. Visible to all users."""
    query: dict = {}
    if external_girl_id:
        query["external_girl_id"] = oid(external_girl_id)
    if caller_id:
        query["caller_id"] = oid(caller_id)
    if status_:
        query["status"] = status_
    if purpose:
        query["purpose"] = purpose
    if start_date or end_date:
        s, e = day_range(start_date or date(2000, 1, 1), end_date or date(2100, 1, 1))
        query["call_date"] = {"$gte": s, "$lt": e}

    sort = [("call_date", -1), ("created_at", -1)]
    result = await paginate(db[c.EXTERNAL_CALLS], query, pg.page, pg.page_size, sort=sort)
    return result


@router.post("/external-calls", status_code=status.HTTP_201_CREATED)
async def create_external_call(
    body: ExternalCallCreate,
    db: Db,
    user: CurrentUser,
):
    """Record or plan a call to an external girl (replaces house visit).

    Includes observations and notes (with speech to text on frontend),
    risk indicators, purpose and status, but excludes location, photo and people met.
    """
    girl = await get_or_404(db[c.EXTERNAL_GIRLS], body.external_girl_id, "External girl")
    now = utcnow()
    call_dt = to_dt(body.call_date)

    doc = {
        "external_girl_id": girl["_id"],
        "external_girl_name": girl.get("name"),
        "external_girl_phone": body.phone_called or girl.get("phone"),
        "location": girl.get("location"),
        "caller_id": user["_id"],
        "caller_name": user.get("name") or user.get("username"),
        "call_date": call_dt,
        "status": body.status,
        "purpose": body.purpose,
        "phone_called": body.phone_called or girl.get("phone"),
        "duration_minutes": body.duration_minutes,
        "risk_indicators": body.risk_indicators or {},
        "observations": body.observations,
        "notes": body.notes,
        "created_by": user["_id"],
        "created_at": now,
        "updated_at": now,
    }
    res = await db[c.EXTERNAL_CALLS].insert_one(doc)

    # Update summary on the girl's document
    await db[c.EXTERNAL_GIRLS].update_one(
        {"_id": girl["_id"]},
        {
            "$inc": {"call_summary.total_calls": 1},
            "$set": {
                "call_summary.last_call_at": call_dt,
                "call_summary.last_call_status": body.status,
                "call_summary.last_caller_name": user.get("name") or user.get("username"),
                "updated_at": now,
            },
        },
    )

    await audit.log(
        db,
        user,
        "create",
        "external_call",
        res.inserted_id,
        f"Recorded call ({body.status}) to {girl.get('name')}",
    )
    return serialize(doc)


@router.get("/external-calls/{call_id}")
async def get_external_call(
    call_id: str,
    db: Db,
    user: CurrentUser,
):
    """Get single call details."""
    call = await get_or_404(db[c.EXTERNAL_CALLS], call_id, "External call")
    return serialize(call)


@router.patch("/external-calls/{call_id}")
async def update_external_call(
    call_id: str,
    body: ExternalCallUpdate,
    db: Db,
    user: CurrentUser,
):
    """Update call record."""
    before = await get_or_404(db[c.EXTERNAL_CALLS], call_id, "External call")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return serialize(before)

    if "call_date" in updates:
        updates["call_date"] = to_dt(updates["call_date"])
    updates["updated_at"] = utcnow()

    await db[c.EXTERNAL_CALLS].update_one({"_id": before["_id"]}, {"$set": updates})
    after = await db[c.EXTERNAL_CALLS].find_one({"_id": before["_id"]})
    await audit.log(
        db,
        user,
        "update",
        "external_call",
        before["_id"],
        f"Updated call to {before.get('external_girl_name')}",
        diff(before, after),
    )
    return serialize(after)


@router.delete("/external-calls/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_external_call(
    call_id: str,
    db: Db,
    user: CurrentUser,
):
    """Delete a call record."""
    call = await get_or_404(db[c.EXTERNAL_CALLS], call_id, "External call")
    await db[c.EXTERNAL_CALLS].delete_one({"_id": call["_id"]})
    # Decrement total calls count on external girl
    await db[c.EXTERNAL_GIRLS].update_one(
        {"_id": call["external_girl_id"]},
        {"$inc": {"call_summary.total_calls": -1}},
    )
    await audit.log(
        db,
        user,
        "delete",
        "external_call",
        call["_id"],
        f"Deleted call to {call.get('external_girl_name')}",
    )
