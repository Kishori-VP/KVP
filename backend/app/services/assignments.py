"""Volunteer (Tai) <-> village assignment.

Rules enforced here:
- A Tai can be assigned to multiple villages concurrently.
- Groups assigned to a Tai must be Kishori Groups of the assigned villages.
- Every reassignment/unassignment closes the assignment record and keeps it as history.
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
            status.HTTP_422_UNPROCESSABLE_CONTENT, "All groups must belong to the specified village"
        )
    return list(dict.fromkeys(ids))


async def current_assignments(db: AsyncDatabase, volunteer_id: ObjectId) -> list[dict]:
    return await db[c.VOLUNTEER_ASSIGNMENTS].find({"volunteer_id": volunteer_id, "is_current": True}).to_list()


async def current_assignment(db: AsyncDatabase, volunteer_id: ObjectId, village_id: ObjectId | None = None) -> dict | None:
    query = {"volunteer_id": volunteer_id, "is_current": True}
    if village_id:
        query["village_id"] = oid(village_id)
    return await db[c.VOLUNTEER_ASSIGNMENTS].find_one(query)


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

    # Check if volunteer is already assigned to THIS specific village
    existing = await db[c.VOLUNTEER_ASSIGNMENTS].find_one({
        "volunteer_id": volunteer["_id"],
        "village_id": village["_id"],
        "is_current": True,
    })

    if existing:
        # Update groups for this existing village assignment
        if set(existing.get("group_ids", [])) == set(groups):
            return existing
        await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
            {"_id": existing["_id"]},
            {"$set": {"group_ids": groups, "updated_at": now}}
        )
        assignment = {**existing, "group_ids": groups}
    else:
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
            "previous_assignment_id": None,
            "created_at": now,
        }
        res = await db[c.VOLUNTEER_ASSIGNMENTS].insert_one(assignment)
        assignment["_id"] = res.inserted_id

    # Update groups ownership
    if groups:
        await db[c.GROUPS].update_many(
            {"_id": {"$in": groups}}, {"$set": {"responsible_volunteer_id": volunteer["_id"], "updated_at": now}}
        )

    # Maintain user's village_ids and village_id (newly assigned village becomes primary)
    existing_village_ids = [v for v in (volunteer.get("village_ids") or []) if v != village["_id"]]
    if volunteer.get("village_id") and volunteer["village_id"] != village["_id"] and volunteer["village_id"] not in existing_village_ids:
        existing_village_ids.append(volunteer["village_id"])
    existing_village_ids.insert(0, village["_id"])

    existing_group_ids = list(set((volunteer.get("group_ids") or []) + groups))

    await db[c.USERS].update_one(
        {"_id": volunteer["_id"]},
        {
            "$set": {
                "village_id": village["_id"],
                "village_ids": existing_village_ids,
                "taluka_id": village["taluka_id"],
                "group_ids": existing_group_ids,
                "updated_at": now,
            }
        },
    )
    return assignment


async def unassign_village(
    db: AsyncDatabase,
    volunteer: dict,
    village_id,
    actor: dict,
    reason: str,
) -> None:
    vid = oid(village_id)
    now = utcnow()
    await db[c.VOLUNTEER_ASSIGNMENTS].update_many(
        {"volunteer_id": volunteer["_id"], "village_id": vid, "is_current": True},
        {"$set": {"is_current": False, "end_date": to_dt(today_local()), "ended_by": actor["_id"], "end_reason": reason}},
    )
    # Release groups of this village
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer["_id"], "village_id": vid},
        {"$set": {"responsible_volunteer_id": None, "updated_at": now}},
    )
    # Update user's village_ids
    existing_vids = [v for v in (volunteer.get("village_ids") or []) if v != vid]
    if not existing_vids and volunteer.get("village_id") and volunteer["village_id"] != vid:
        existing_vids = [volunteer["village_id"]]
    
    primary_vid = existing_vids[0] if existing_vids else None
    primary_taluka = None
    if primary_vid:
        vdoc = await db[c.VILLAGES].find_one({"_id": primary_vid})
        primary_taluka = vdoc.get("taluka_id") if vdoc else None

    # Filter remaining groups
    remaining_groups = await db[c.GROUPS].find(
        {"_id": {"$in": volunteer.get("group_ids", [])}, "village_id": {"$ne": vid}}, {"_id": 1}
    ).to_list()
    remaining_group_ids = [g["_id"] for g in remaining_groups]

    await db[c.USERS].update_one(
        {"_id": volunteer["_id"]},
        {
            "$set": {
                "village_id": primary_vid,
                "village_ids": existing_vids,
                "taluka_id": primary_taluka,
                "group_ids": remaining_group_ids,
                "updated_at": now,
            }
        },
    )


async def end_assignment(db: AsyncDatabase, volunteer: dict, actor: dict, reason: str) -> None:
    """Used when a Tai is changed to Stakeholder or deactivated."""
    now = utcnow()
    await db[c.VOLUNTEER_ASSIGNMENTS].update_many(
        {"volunteer_id": volunteer["_id"], "is_current": True},
        {"$set": {"is_current": False, "end_date": to_dt(today_local()), "ended_by": actor["_id"], "end_reason": reason}},
    )
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer["_id"]}, {"$set": {"responsible_volunteer_id": None, "updated_at": now}}
    )
    await db[c.USERS].update_one(
        {"_id": volunteer["_id"]},
        {"$set": {"village_id": None, "village_ids": [], "taluka_id": None, "group_ids": [], "updated_at": now}},
    )


async def set_groups(db: AsyncDatabase, volunteer: dict, group_ids: list, village_id: ObjectId | None = None) -> list[ObjectId]:
    vid = village_id or volunteer.get("village_id")
    if not vid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tai has no assigned village")
    groups = await validate_groups(db, oid(vid), group_ids)
    now = utcnow()
    await db[c.GROUPS].update_many(
        {"responsible_volunteer_id": volunteer["_id"], "village_id": oid(vid), "_id": {"$nin": groups}},
        {"$set": {"responsible_volunteer_id": None, "updated_at": now}},
    )
    if groups:
        await db[c.GROUPS].update_many(
            {"_id": {"$in": groups}}, {"$set": {"responsible_volunteer_id": volunteer["_id"], "updated_at": now}}
        )
    # Combine with groups from other villages
    other_groups = await db[c.GROUPS].find(
        {"responsible_volunteer_id": volunteer["_id"], "village_id": {"$ne": oid(vid)}}, {"_id": 1}
    ).to_list()
    all_group_ids = list(set([g["_id"] for g in other_groups] + groups))

    await db[c.USERS].update_one({"_id": volunteer["_id"]}, {"$set": {"group_ids": all_group_ids, "updated_at": now}})
    await db[c.VOLUNTEER_ASSIGNMENTS].update_one(
        {"volunteer_id": volunteer["_id"], "village_id": oid(vid), "is_current": True},
        {"$set": {"group_ids": groups}},
    )
    return groups


async def handover_village(
    db: AsyncDatabase,
    from_volunteer: dict,
    to_volunteer: dict,
    village_id,
    actor: dict,
    reason: str,
    transfer_groups: bool = True,
    transfer_cases: bool = True,
    transfer_targets: bool = False,
    effective_date: date | None = None,
) -> dict:
    """Hand over a village from one Tai to another Tai.

    - Unassigns the village from the source volunteer (saving assignment history).
    - Assigns the village to the target volunteer.
    - Optionally transfers all Kishori Groups of this village to the new volunteer.
    - Optionally transfers all active/open cases in this village to the new volunteer.
    - Optionally transfers active targets to the new volunteer.
    """
    vid = oid(village_id)
    if from_volunteer["_id"] == to_volunteer["_id"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Source and target Tais must be different")
    if not to_volunteer.get("is_active"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot hand over village to an inactive volunteer")
    if not from_volunteer.get("is_active"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot hand over village from an inactive volunteer")

    village = await load_active_village(db, vid)

    # Verify source Tai is assigned to this village
    from_village_ids = [v for v in (from_volunteer.get("village_ids") or [])]
    if from_volunteer.get("village_id") and from_volunteer["village_id"] not in from_village_ids:
        from_village_ids.append(from_volunteer["village_id"])

    has_assignment = vid in from_village_ids or await db[c.VOLUNTEER_ASSIGNMENTS].find_one({
        "volunteer_id": from_volunteer["_id"],
        "village_id": vid,
        "is_current": True,
    })
    if not has_assignment:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Source Tai is not currently assigned to this village")

    # Verify target Tai is not already assigned to this village
    to_village_ids = [v for v in (to_volunteer.get("village_ids") or [])]
    if to_volunteer.get("village_id") and to_volunteer["village_id"] not in to_village_ids:
        to_village_ids.append(to_volunteer["village_id"])
    if vid in to_village_ids:
        raise HTTPException(status.HTTP_409_CONFLICT, "Target Tai is already assigned to this village")

    # Determine groups of this village to transfer
    group_ids = []
    if transfer_groups:
        groups_cursor = await db[c.GROUPS].find(
            {"village_id": vid, "$or": [{"responsible_volunteer_id": from_volunteer["_id"]}, {"_id": {"$in": from_volunteer.get("group_ids", [])}}]},
            {"_id": 1}
        ).to_list()
        group_ids = [g["_id"] for g in groups_cursor]
        if not group_ids:
            all_v_groups = await db[c.GROUPS].find({"village_id": vid}, {"_id": 1}).to_list()
            group_ids = [g["_id"] for g in all_v_groups]

    # 1. Unassign from source volunteer
    await unassign_village(
        db, from_volunteer, vid, actor, f"Handed over to {to_volunteer.get('name', 'another Tai')}: {reason}"
    )

    # Refresh to_volunteer document before assigning
    fresh_to = await db[c.USERS].find_one({"_id": to_volunteer["_id"]})

    # 2. Assign to target volunteer
    assignment = await assign_village(
        db,
        fresh_to,
        vid,
        group_ids,
        actor,
        f"Handed over from {from_volunteer.get('name', 'another Tai')}: {reason}",
        start_date=effective_date,
    )

    # 3. Transfer open cases if requested
    cases_transferred = 0
    if transfer_cases:
        from app.services.beneficiaries import OPEN_CASE_STATUSES
        now = utcnow()
        cases = await db[c.CASES].find({
            "village_id": vid,
            "assigned_to": from_volunteer["_id"],
            "status": {"$in": OPEN_CASE_STATUSES},
        }).to_list()

        for cs in cases:
            await db[c.CASES].update_one(
                {"_id": cs["_id"]},
                {
                    "$set": {"assigned_to": to_volunteer["_id"], "updated_at": now},
                    "$push": {
                        "timeline": {
                            "at": now,
                            "by": actor["_id"],
                            "by_name": actor.get("name"),
                            "type": "handover",
                            "text": f"Handed over from {from_volunteer.get('name')} to {to_volunteer.get('name')}: {reason}",
                            "assigned_to": to_volunteer["_id"],
                        }
                    },
                },
            )
            cases_transferred += 1

    # 4. Transfer active targets if requested
    targets_transferred = 0
    if transfer_targets:
        now = utcnow()
        targets = await db[c.TARGETS].find({
            "volunteer_id": from_volunteer["_id"],
            "status": "active",
        }).to_list()
        for tg in targets:
            await db[c.TARGETS].update_one(
                {"_id": tg["_id"]},
                {
                    "$set": {"volunteer_id": to_volunteer["_id"], "updated_at": now},
                    "$push": {
                        "revisions": {
                            "at": now,
                            "by": actor["_id"],
                            "by_name": actor.get("name"),
                            "reason": f"Village handover: {reason}",
                            "changes": {"volunteer_id": {"from": str(from_volunteer["_id"]), "to": str(to_volunteer["_id"])}},
                        }
                    },
                },
            )
            targets_transferred += 1

    return {
        "assignment": assignment,
        "village": village,
        "group_ids": group_ids,
        "cases_transferred": cases_transferred,
        "targets_transferred": targets_transferred,
    }

