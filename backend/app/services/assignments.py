"""Volunteer <-> village assignment (PRD 4.1 / 4.2).

Rules enforced here:
- A Volunteer can work in several villages at once; each village is one current
  assignment (a partial unique index on volunteer_assignments prevents assigning
  the same village twice).
- Groups assigned to a Volunteer must be Kishori Groups of one of her villages.
- Every change closes the affected assignment and keeps it as history.
- users.village_ids (and the "primary" users.village_id = the earliest current
  village) are always recomputed from the current assignments.
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


async def validate_groups(db: AsyncDatabase, village_ids, group_ids: list) -> list[ObjectId]:
    """All groups must belong to the given village (or to one of the given villages)."""
    ids = oids(group_ids)
    if not ids:
        return []
    villages = list(village_ids) if isinstance(village_ids, (list, tuple, set)) else [village_ids]
    found = await db[c.GROUPS].count_documents({"_id": {"$in": ids}, "village_id": {"$in": villages}})
    if found != len(set(ids)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "All groups must belong to the volunteer's assigned villages"
        )
    return list(dict.fromkeys(ids))


async def current_assignments(db: AsyncDatabase, volunteer_id: ObjectId) -> list[dict]:
    return await db[c.VOLUNTEER_ASSIGNMENTS].find({"volunteer_id": volunteer_id, "is_current": True}).sort(
        [("start_date", 1), ("created_at", 1)]).to_list()


async def current_assignment(db: AsyncDatabase, volunteer_id: ObjectId, village_id=None) -> dict | None:
    q: dict = {"volunteer_id": volunteer_id, "is_current": True}
    if village_id:
        q["village_id"] = oid(village_id)
    return await db[c.VOLUNTEER_ASSIGNMENTS].find_one(q, sort=[("start_date", 1), ("created_at", 1)])


async def sync_user(db: AsyncDatabase, volunteer_id: ObjectId) -> dict:
    """Recompute the volunteer's village and group fields from her current assignments."""
    current = await current_assignments(db, volunteer_id)
    village_ids = [a["village_id"] for a in current]
    group_ids = list(dict.fromkeys(g for a in current for g in a.get("group_ids", [])))
    sets = {
        "village_ids": village_ids,
        "village_id": village_ids[0] if village_ids else None,
        "taluka_id": current[0]["taluka_id"] if current else None,
        "group_ids": group_ids,
        "updated_at": utcnow(),
    }
    await db[c.USERS].update_one({"_id": volunteer_id}, {"$set": sets})
    return sets


async def _release_groups(db: AsyncDatabase, volunteer_id: ObjectId, village_id: ObjectId) -> None:
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer_id, "village_id": village_id},
        {"$set": {"responsible_volunteer_id": None, "updated_at": utcnow()}},
    )


async def _close(db: AsyncDatabase, assignment: dict, actor: dict, reason: str, end: date) -> None:
    await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
        {"_id": assignment["_id"]},
        {"$set": {"is_current": False, "end_date": to_dt(end), "ended_by": actor["_id"], "end_reason": reason}},
    )
    await _release_groups(db, assignment["volunteer_id"], assignment["village_id"])


async def assign_village(
    db: AsyncDatabase,
    volunteer: dict,
    village_id,
    group_ids: list,
    actor: dict,
    reason: str,
    start_date: date | None = None,
    replaces_village_id=None,
) -> dict:
    """Add a village to the volunteer. With replaces_village_id, that village's assignment is closed
    first (a move); otherwise her other villages stay as they are."""
    village = await load_active_village(db, village_id)
    groups = await validate_groups(db, village["_id"], group_ids)
    start = start_date or today_local()
    now = utcnow()

    existing = await current_assignment(db, volunteer["_id"], village["_id"])
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Volunteer is already assigned to {village['name']}")
    previous = None
    if replaces_village_id:
        previous = await current_assignment(db, volunteer["_id"], replaces_village_id)
        if not previous:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The volunteer is not assigned to the village being replaced")
        await _close(db, previous, actor, reason, start)

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
    await sync_user(db, volunteer["_id"])
    return assignment


async def remove_village(db: AsyncDatabase, volunteer: dict, village_id, actor: dict, reason: str,
                         end_date: date | None = None) -> dict:
    """Close the volunteer's assignment to one village; her other villages are unaffected."""
    current = await current_assignment(db, volunteer["_id"], village_id)
    if not current:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The volunteer is not assigned to this village")
    await _close(db, current, actor, reason, end_date or today_local())
    return await sync_user(db, volunteer["_id"])


async def end_assignment(db: AsyncDatabase, volunteer: dict, actor: dict, reason: str) -> None:
    """Close all current assignments (used when a Volunteer is changed to Stakeholder)."""
    for a in await current_assignments(db, volunteer["_id"]):
        await _close(db, a, actor, reason, today_local())
    await db[c.USERS].update_one(
        {"_id": volunteer["_id"]},
        {"$set": {"village_ids": [], "village_id": None, "taluka_id": None, "group_ids": [], "updated_at": utcnow()}},
    )


async def set_groups(db: AsyncDatabase, volunteer: dict, group_ids: list) -> list[ObjectId]:
    """Replace the volunteer's groups; each group is stored on the assignment of its own village."""
    current = await current_assignments(db, volunteer["_id"])
    if not current:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Volunteer has no assigned village")
    groups = await validate_groups(db, [a["village_id"] for a in current], group_ids)
    group_village = {g["_id"]: g["village_id"] async for g in db[c.GROUPS].find({"_id": {"$in": groups}}, {"village_id": 1})}
    now = utcnow()
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer["_id"], "_id": {"$nin": groups}},
        {"$set": {"responsible_volunteer_id": None, "updated_at": now}},
    )
    if groups:
        await db[c.GROUPS].update_many(
            {"_id": {"$in": groups}}, {"$set": {"responsible_volunteer_id": volunteer["_id"], "updated_at": now}}
        )
    for a in current:
        await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
            {"_id": a["_id"]}, {"$set": {"group_ids": [g for g in groups if group_village.get(g) == a["village_id"]]}}
        )
    await sync_user(db, volunteer["_id"])
    return groups
