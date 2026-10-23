"""Programme master data: talukas, villages, Kishori / Bal Panchayat groups (PRD 4.2, 4.18)."""

import re

from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.deps import CurrentUser, Db, Pagination, Stakeholder, group_scope, user_village_ids, village_scope
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.master import (
    GroupCreate,
    GroupType,
    GroupUpdate,
    TalukaCreate,
    TalukaUpdate,
    VillageCreate,
    VillageLocationsUpdate,
    VillageUpdate,
)
from app.services import audit
from app.services.counters import next_code
from app.services.lookups import MANDATORY_CONTACT_CATEGORIES
from app.utils.dates import utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, oids, paginate, serialize
from app.utils.translit import to_latin

router = APIRouter(tags=["master data"])


def _conflict(what: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, f"{what} already exists")


async def _update(db, coll: str, id_: str, label: str, updates: dict, actor: dict, entity: str) -> dict:
    before = await get_or_404(db[coll], id_, label)
    if not updates:
        return serialize(before)
    updates["updated_at"] = utcnow()
    try:
        await db[coll].update_one({"_id": before["_id"]}, {"$set": updates})
    except DuplicateKeyError:
        raise _conflict(label)
    after = await db[coll].find_one({"_id": before["_id"]})
    await audit.log(db, actor, "update", entity, before["_id"], f"Updated {label.lower()} {after.get('name')}",
                    diff(before, after))
    return serialize(after)


# ---------------------------------------------------------------- talukas

@router.post("/talukas", status_code=status.HTTP_201_CREATED)
async def create_taluka(body: TalukaCreate, db: Db, actor: Stakeholder):
    now = utcnow()
    doc = {**body.model_dump(), "code": await next_code(db, c.TALUKAS, {}), "created_at": now, "updated_at": now}
    try:
        res = await db[c.TALUKAS].insert_one(doc)
    except DuplicateKeyError:
        raise _conflict("Taluka")
    await audit.log(db, actor, "create", "taluka", res.inserted_id, f"Created taluka {body.name}")
    return serialize(doc)


@router.get("/talukas")
async def list_talukas(db: Db, _: CurrentUser, district: str | None = None, include_inactive: bool = False):
    query: dict = {} if include_inactive else {"is_active": True}
    if district:
        query["district"] = district
    talukas = await db[c.TALUKAS].find(query).sort("name", 1).to_list()
    counts = {
        d["_id"]: d["n"]
        async for d in await db[c.VILLAGES].aggregate([{"$group": {"_id": "$taluka_id", "n": {"$sum": 1}}}])
    }
    return [{**serialize(t), "village_count": counts.get(t["_id"], 0)} for t in talukas]


@router.get("/districts")
async def list_districts(db: Db, _: CurrentUser):
    """District -> taluka hierarchy."""
    pipeline = [
        {"$match": {"is_active": True}},
        {"$sort": {"name": 1}},
        {"$group": {"_id": "$district", "talukas": {"$push": {"id": {"$toString": "$_id"}, "name": "$name",
                                                              "name_mr": "$name_mr"}}}},
        {"$sort": {"_id": 1}},
    ]
    return [{"district": d["_id"], "talukas": d["talukas"]} async for d in await db[c.TALUKAS].aggregate(pipeline)]


@router.patch("/talukas/{taluka_id}")
async def update_taluka(taluka_id: str, body: TalukaUpdate, db: Db, actor: Stakeholder):
    updates = body.model_dump(exclude_unset=True)
    result = await _update(db, c.TALUKAS, taluka_id, "Taluka", updates, actor, "taluka")
    if "district" in updates:
        await db[c.VILLAGES].update_many({"taluka_id": oid(taluka_id)}, {"$set": {"district": updates["district"]}})
    return result


# ---------------------------------------------------------------- villages

@router.post("/villages", status_code=status.HTTP_201_CREATED)
async def create_village(body: VillageCreate, db: Db, actor: Stakeholder):
    taluka = await get_or_404(db[c.TALUKAS], body.taluka_id, "Taluka")
    now = utcnow()
    doc = {
        **body.model_dump(exclude={"taluka_id", "location"}),
        "taluka_id": taluka["_id"],
        "district": taluka["district"],
        "location": body.location.model_dump() if body.location else None,
        # Village number within its taluka, used in Girl IDs (KVP-<taluka>-<village>-<girl>).
        "code": await next_code(db, c.VILLAGES, {"taluka_id": taluka["_id"]}),
        "created_at": now,
        "updated_at": now,
    }
    try:
        res = await db[c.VILLAGES].insert_one(doc)
    except DuplicateKeyError:
        raise _conflict("Village in this taluka")
    await audit.log(db, actor, "create", "village", res.inserted_id, f"Created village {body.name}")
    return serialize(doc)


@router.get("/villages")
async def list_villages(
    db: Db,
    user: CurrentUser,
    taluka_id: ObjectIdStr | None = None,
    district: str | None = None,
    status_: str | None = Query(None, alias="status"),
    q: str | None = None,
):
    query: dict = village_scope(user, "_id")
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if district:
        query["district"] = district
    if status_:
        query["status"] = status_
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"name_mr": rx}, {"aliases": rx}, {"hamlets": rx}]
    villages = await db[c.VILLAGES].find(query).sort("name", 1).to_list()
    ids = [v["_id"] for v in villages]

    async def count_by(coll, match):
        pipeline = [{"$match": {"village_id": {"$in": ids}, **match}}, {"$group": {"_id": "$village_id", "n": {"$sum": 1}}}]
        return {d["_id"]: d["n"] async for d in await db[coll].aggregate(pipeline)}

    girls = await count_by(c.GIRLS, {"is_deleted": {"$ne": True}})
    groups = await count_by(c.GROUPS, {"group_type": "kishori", "is_active": True})
    vols = await count_by(c.USERS, {"role": Role.VOLUNTEER.value, "is_active": True})
    talukas = {t["_id"]: t for t in await db[c.TALUKAS].find().to_list()}
    return [
        {
            **serialize(v),
            "taluka_name": talukas.get(v["taluka_id"], {}).get("name"),
            "girl_count": girls.get(v["_id"], 0),
            "kishori_group_count": groups.get(v["_id"], 0),
            "volunteer_count": vols.get(v["_id"], 0),
        }
        for v in villages
    ]


@router.put("/villages/locations")
async def bulk_update_locations(body: VillageLocationsUpdate, db: Db, actor: Stakeholder):
    """Set coordinates (and PIN codes) for many villages at once, for the village map."""
    ids = [oid(i.village_id) for i in body.items]
    found = {v["_id"]: v async for v in db[c.VILLAGES].find({"_id": {"$in": ids}})}
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown villages: {missing}")
    now = utcnow()
    for item in body.items:
        v = found[oid(item.village_id)]
        sets = {"location": {"lat": item.lat, "lng": item.lng}, "updated_at": now}
        if item.pin_code:
            sets["pin_code"] = item.pin_code
        await db[c.VILLAGES].update_one({"_id": v["_id"]}, {"$set": sets})
        await audit.log(db, actor, "update", "village", v["_id"], f"Set location for {v['name']}",
                        diff(v, {**v, **sets}, ["location", "pin_code"]))
    return {"updated": len(body.items)}


@router.get("/villages/{village_id}")
async def get_village(village_id: str, db: Db, user: CurrentUser):
    if user["role"] == Role.VOLUNTEER and oid(village_id) not in user_village_ids(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your assigned village")
    village = await get_or_404(db[c.VILLAGES], village_id, "Village")
    vid = village["_id"]
    taluka = await db[c.TALUKAS].find_one({"_id": village["taluka_id"]})
    groups = await db[c.GROUPS].find({"$or": [{"village_id": vid}, {"member_village_ids": vid}]}).sort(
        [("group_type", 1), ("name", 1)]).to_list()
    volunteers = await db[c.USERS].find(
        {"village_id": vid, "role": Role.VOLUNTEER.value}, {"name": 1, "phone": 1, "is_active": 1, "group_ids": 1}
    ).to_list()
    contacts = await db[c.CONTACTS].find({"village_id": vid, "is_active": True}).to_list()
    present = {ct["category"] for ct in contacts}
    girl_counts = {
        d["_id"]: d["n"]
        async for d in await db[c.GIRLS].aggregate([
            {"$match": {"village_id": vid, "is_deleted": {"$ne": True}}},
            {"$group": {"_id": "$group_id", "n": {"$sum": 1}}},
        ])
    }
    return {
        **serialize(village),
        "taluka": serialize(taluka),
        "girl_count": sum(girl_counts.values()),
        "girls_without_group": girl_counts.get(None, 0),
        "groups": [{**serialize(g), "girl_count": girl_counts.get(g["_id"], 0)} for g in groups],
        "volunteers": serialize(volunteers),
        "contacts": serialize(contacts),
        "missing_mandatory_contacts": [cat for cat in MANDATORY_CONTACT_CATEGORIES if cat not in present],
    }


@router.patch("/villages/{village_id}")
async def update_village(village_id: str, body: VillageUpdate, db: Db, actor: Stakeholder):
    updates = body.model_dump(exclude_unset=True)
    if "taluka_id" in updates:
        taluka = await get_or_404(db[c.TALUKAS], updates["taluka_id"], "Taluka")
        updates["taluka_id"] = taluka["_id"]
        updates["district"] = taluka["district"]
    if updates.get("location") is not None:
        updates["location"] = body.location.model_dump()
    result = await _update(db, c.VILLAGES, village_id, "Village", updates, actor, "village")
    if "taluka_id" in updates:
        # Keep denormalised taluka references in sync.
        vid = oid(village_id)
        for coll in (c.GIRLS, c.USERS, c.CONTACTS):
            await db[coll].update_many({"village_id": vid}, {"$set": {"taluka_id": updates["taluka_id"]}})
    return result


# ---------------------------------------------------------------- groups

async def _member_villages(db, ids: list, home_village_id) -> list:
    """Validate a group's member villages; the home village itself is never listed."""
    members = [v for v in dict.fromkeys(oids(ids)) if v != home_village_id]
    if members and await db[c.VILLAGES].count_documents({"_id": {"$in": members}}) != len(members):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member village not found")
    return members


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, db: Db, actor: Stakeholder):
    village = await get_or_404(db[c.VILLAGES], body.village_id, "Village")
    vol_id = await _check_responsible(db, body.responsible_volunteer_id, village["_id"])
    members = await _member_villages(db, body.member_village_ids, village["_id"])
    now = utcnow()
    doc = {
        **body.model_dump(exclude={"village_id", "member_village_ids", "responsible_volunteer_id", "meeting_schedule"}),
        "member_village_ids": members,
        "name_en": to_latin(body.name),
        "village_id": village["_id"],
        "taluka_id": village["taluka_id"],
        "responsible_volunteer_id": vol_id,
        "meeting_schedule": body.meeting_schedule.model_dump() if body.meeting_schedule else None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        res = await db[c.GROUPS].insert_one(doc)
    except DuplicateKeyError:
        raise _conflict("A group with this name in this village")
    if vol_id:
        await db[c.USERS].update_one({"_id": vol_id}, {"$addToSet": {"group_ids": res.inserted_id}})
    await audit.log(db, actor, "create", "group", res.inserted_id, f"Created {body.group_type} group {body.name}")
    return serialize(doc)


async def _check_responsible(db, volunteer_id, village_id):
    if not volunteer_id:
        return None
    vol = await db[c.USERS].find_one({"_id": oid(volunteer_id), "role": Role.VOLUNTEER.value})
    if not vol:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Volunteer not found")
    if village_id not in user_village_ids(vol):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Responsible volunteer must be assigned to this village")
    return vol["_id"]


@router.get("/groups")
async def list_groups(
    db: Db,
    user: CurrentUser,
    pg: Pagination,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    group_type: GroupType | None = None,
    responsible_volunteer_id: ObjectIdStr | None = None,
    include_inactive: bool = False,
):
    query: dict = group_scope(user, village_id)
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if group_type:
        query["group_type"] = group_type
    if responsible_volunteer_id:
        query["responsible_volunteer_id"] = oid(responsible_volunteer_id)
    if not include_inactive:
        query["is_active"] = True
    return await paginate(db[c.GROUPS], query, pg.page, pg.page_size, sort=[("village_id", 1), ("name", 1)])


@router.get("/groups/{group_id}")
async def get_group(group_id: str, db: Db, user: CurrentUser):
    group = await get_or_404(db[c.GROUPS], group_id, "Group", group_scope(user))
    girls = await db[c.GIRLS].find(
        {"group_id": group["_id"], "is_deleted": {"$ne": True}}, {"girl_code": 1, "name": 1, "dob": 1, "age": 1}
    ).sort("girl_code", 1).to_list()
    return {**serialize(group), "girls": serialize(girls), "girl_count": len(girls)}


@router.patch("/groups/{group_id}")
async def update_group(group_id: str, body: GroupUpdate, db: Db, actor: Stakeholder):
    group = await get_or_404(db[c.GROUPS], group_id, "Group")
    updates = body.model_dump(exclude_unset=True)
    if "responsible_volunteer_id" in updates:
        new_vol = await _check_responsible(db, updates["responsible_volunteer_id"], group["village_id"])
        updates["responsible_volunteer_id"] = new_vol
        old_vol = group.get("responsible_volunteer_id")
        if old_vol and old_vol != new_vol:
            await db[c.USERS].update_one({"_id": old_vol}, {"$pull": {"group_ids": group["_id"]}})
        if new_vol:
            await db[c.USERS].update_one({"_id": new_vol}, {"$addToSet": {"group_ids": group["_id"]}})
    if updates.get("meeting_schedule") is not None:
        updates["meeting_schedule"] = body.meeting_schedule.model_dump()
    if updates.get("name"):
        updates["name_en"] = to_latin(updates["name"])
    if updates.get("member_village_ids") is not None:
        updates["member_village_ids"] = await _member_villages(db, updates["member_village_ids"], group["village_id"])
    elif "member_village_ids" in updates:
        updates["member_village_ids"] = []
    return await _update(db, c.GROUPS, group_id, "Group", updates, actor, "group")
