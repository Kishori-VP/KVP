"""Volunteer <-> village assignment (PRD 4.1 / 4.2).

Rules enforced here:
- A Volunteer has exactly one current village assignment (also guaranteed by a
  partial unique index on volunteer_assignments).
- Groups assigned to a Volunteer must be Kishori Groups of that same village.
- Every change closes the previous assignment and keeps it as history.
"""

from datetime import date

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.utils.dates import to_dt, today_local, utcnow
from app.utils.mongo import oid, oids


async def load_active_village(db: AsyncDatabase, village_id) -> dict:
    village = await db[c.VILLAGES].find_one({"_id": oid(village_id)})
    if not village:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Village not found")
    if village.get("status") != "active":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Village is inactive")
    return village


async def validate_groups(db: AsyncDatabase, village_id: ObjectId, group_ids: list) -> list[ObjectId]:
    ids = oids(group_ids)
    if not ids:
        return []
    found = await db[c.GROUPS].count_documents({"_id": {"$in": ids}, "village_id": village_id})
    if found != len(set(ids)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "All groups must belong to the volunteer's assigned village"
        )
    return list(dict.fromkeys(ids))


async def current_assignment(db: AsyncDatabase, volunteer_id: ObjectId) -> dict | None:
    return await db[c.VOLUNTEER_ASSIGNMENTS].find_one({"volunteer_id": volunteer_id, "is_current": True})


async def assign_village(
    db: AsyncDatabase,
    volunteer: dict,
    village_id,
    group_ids: list,
    actor: dict,
    reason: str,
    start_date: date | None = None,
) -> dict:
    village = await load_active_village(db, village_id)
    groups = await validate_groups(db, village["_id"], group_ids)
    start = start_date or today_local()
    now = utcnow()

    previous = await current_assignment(db, volunteer["_id"])
    if previous:
        if previous["village_id"] == village["_id"] and set(previous.get("group_ids", [])) == set(groups):
            raise HTTPException(status.HTTP_409_CONFLICT, "Volunteer is already assigned to this village and groups")
        await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
            {"_id": previous["_id"]},
            {"$set": {"is_current": False, "end_date": to_dt(start), "ended_by": actor["_id"], "end_reason": reason}},
        )
        # Release groups this volunteer was responsible for.
        await db[c.GROUPS].update_many(
            {"responsible_volunteer_id": volunteer["_id"]},
            {"$set": {"responsible_volunteer_id": None, "updated_at": now}},
        )

    assignment = {
        "volunteer_id": volunteer["_id"],
        "village_id": village["_id"],
        "taluka_id": village["taluka_id"],
        "group_ids": groups,
        "start_date": to_dt(start),
        "end_date": None,
        "is_current": True,
        "assigned_by": actor["_id"],
        "reason": reason,
        "previous_assignment_id": previous["_id"] if previous else None,
        "created_at": now,
    }
    res = await db[c.VOLUNTEER_ASSIGNMENTS].insert_one(assignment)
    assignment["_id"] = res.inserted_id

    if groups:
        await db[c.GROUPS].update_many(
            {"_id": {"$in": groups}}, {"$set": {"responsible_volunteer_id": volunteer["_id"], "updated_at": now}}
        )
    await db[c.USERS].update_one(
        {"_id": volunteer["_id"]},
        {
            "$set": {
                "village_id": village["_id"],
                "taluka_id": village["taluka_id"],
                "group_ids": groups,
                "updated_at": now,
            }
        },
    )
    return assignment


async def end_assignment(db: AsyncDatabase, volunteer: dict, actor: dict, reason: str) -> None:
    """Used when a Volunteer is changed to Stakeholder."""
    now = utcnow()
    await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
        {"volunteer_id": volunteer["_id"], "is_current": True},
        {"$set": {"is_current": False, "end_date": to_dt(today_local()), "ended_by": actor["_id"], "end_reason": reason}},
    )
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer["_id"]}, {"$set": {"responsible_volunteer_id": None, "updated_at": now}}
    )
    await db[c.USERS].update_one(
        {"_id": volunteer["_id"]}, {"$set": {"village_id": None, "taluka_id": None, "group_ids": [], "updated_at": now}}
    )


async def set_groups(db: AsyncDatabase, volunteer: dict, group_ids: list) -> list[ObjectId]:
    if not volunteer.get("village_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Volunteer has no assigned village")
    groups = await validate_groups(db, volunteer["village_id"], group_ids)
    now = utcnow()
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer["_id"], "_id": {"$nin": groups}},
        {"$set": {"responsible_volunteer_id": None, "updated_at": now}},
    )
    if groups:
        await db[c.GROUPS].update_many(
            {"_id": {"$in": groups}}, {"$set": {"responsible_volunteer_id": volunteer["_id"], "updated_at": now}}
        )
    await db[c.USERS].update_one({"_id": volunteer["_id"]}, {"$set": {"group_ids": groups, "updated_at": now}})
    await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
        {"volunteer_id": volunteer["_id"], "is_current": True}, {"$set": {"group_ids": groups}}
    )
    return groups
