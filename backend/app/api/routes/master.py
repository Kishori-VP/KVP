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
    from app.core.deps import is_super_admin
    if not is_super_admin(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin can manage talukas")
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
    from app.core.deps import is_super_admin
    if not is_super_admin(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin can manage talukas")
    updates = body.model_dump(exclude_unset=True)
    result = await _update(db, c.TALUKAS, taluka_id, "Taluka", updates, actor, "taluka")
    if "district" in updates:
        await db[c.VILLAGES].update_many({"taluka_id": oid(taluka_id)}, {"$set": {"district": updates["district"]}})
    return result


# ---------------------------------------------------------------- villages

@router.post("/villages", status_code=status.HTTP_201_CREATED)
async def create_village(body: VillageCreate, db: Db, actor: Stakeholder):
    from app.core.deps import is_super_admin
    if not is_super_admin(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin can manage villages")
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
    vol_pipeline = [
        {"$match": {"role": Role.VOLUNTEER.value, "is_active": True}},
        {"$project": {"vids": {"$cond": [{"$gt": [{"$size": {"$ifNull": ["$village_ids", []]}}, 0]}, "$village_ids", ["$village_id"]]}}},
        {"$unwind": "$vids"},
        {"$match": {"vids": {"$in": ids}}},
        {"$group": {"_id": "$vids", "n": {"$sum": 1}}},
    ]
    vols = {d["_id"]: d["n"] async for d in await db[c.USERS].aggregate(vol_pipeline)}
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
    from app.core.deps import is_super_admin
    if not is_super_admin(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin can update village locations")
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
        {"$or": [{"village_ids": vid}, {"village_id": vid}], "role": Role.VOLUNTEER.value},
        {"name": 1, "phone": 1, "is_active": 1, "group_ids": 1}
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
    bp_counts = {
        d["_id"]: d["n"]
        async for d in await db[c.GIRLS].aggregate([
            {"$match": {"village_id": vid, "is_deleted": {"$ne": True}, "bal_panchayat_id": {"$ne": None}}},
            {"$group": {"_id": "$bal_panchayat_id", "n": {"$sum": 1}}},
        ])
    }
    return {
        **serialize(village),
        "taluka": serialize(taluka),
        "girl_count": sum(girl_counts.values()),
        "girls_without_group": girl_counts.get(None, 0),
        "groups": [{**serialize({k: v for k, v in g.items() if k != "members"}),
                    "girl_count": girl_counts.get(g["_id"], 0) + bp_counts.get(g["_id"], 0),
                    "member_count": len(g.get("members", []))} for g in groups],
        "volunteers": serialize(volunteers),
        "contacts": serialize(contacts),
        "missing_mandatory_contacts": [cat for cat in MANDATORY_CONTACT_CATEGORIES if cat not in present],
    }


@router.patch("/villages/{village_id}")
async def update_village(village_id: str, body: VillageUpdate, db: Db, actor: Stakeholder):
    from app.core.deps import is_super_admin
    if not is_super_admin(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin can update villages")
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
        new_taluka = updates["taluka_id"]
        for coll in (c.GIRLS, c.CONTACTS, c.CASES, c.EVENTS, c.HOME_VISITS, c.ACTIVITY_REPORTS, c.GROUPS):
            await db[coll].update_many({"village_id": vid}, {"$set": {"taluka_id": new_taluka}})
        await db[c.USERS].update_many(
            {"$or": [{"village_id": vid}, {"village_ids": vid}]},
            {"$set": {"taluka_id": new_taluka}}
        )
        await db[c.TARGETS].update_many(
            {"$or": [{"village_id": vid}, {"village_ids": vid}]},
            {"$set": {"taluka_id": new_taluka}}
        )
    return result


# ---------------------------------------------------------------- groups

async def next_group_number(db, village: dict, group_type: str) -> str:
    """Group numbers follow the village code: 01-12-K03 is the 3rd Kishori group of village 12 in taluka 01,
    01-12-BP01 its first Bal Panchayat."""
    taluka = await db[c.TALUKAS].find_one({"_id": village["taluka_id"]}, {"code": 1})
    prefix = f"{int(taluka.get('code') or 0):02d}-{int(village.get('code') or 0):02d}-{'K' if group_type == 'kishori' else 'BP'}"
    taken = await db[c.GROUPS].distinct("group_number", {"group_number": {"$regex": f"^{prefix}" + r"\d+$"}})
    n = max((int(x[len(prefix):]) for x in taken), default=0) + 1
    return f"{prefix}{n:02d}"


async def _member_villages(db, ids: list, home_village_id) -> list:
    """Validate a group's member villages; the home village itself is never listed."""
    members = [v for v in dict.fromkeys(oids(ids)) if v != home_village_id]
    if members and await db[c.VILLAGES].count_documents({"_id": {"$in": members}}) != len(members):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member village not found")
    return members


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, db: Db, actor: Stakeholder):
    from app.core.deps import check_not_read_only
    check_not_read_only(actor)
    village = await get_or_404(db[c.VILLAGES], body.village_id, "Village")
    vol_id = await _check_responsible(db, body.responsible_volunteer_id, village["_id"])
    members = await _member_villages(db, body.member_village_ids, village["_id"])
    now = utcnow()
    if not body.group_number:
        body.group_number = await next_group_number(db, village, body.group_type)
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
    return await paginate(db[c.GROUPS], query, pg.page, pg.page_size, sort=[("group_number", 1), ("name", 1)])


@router.get("/children")
async def list_children(
    db: Db,
    user: CurrentUser,
    pg: Pagination,
    village_id: ObjectIdStr | None = None,
    group_id: ObjectIdStr | None = None,
    q: str | None = None,
    registered: bool | None = Query(None, description="true: linked to a registered girl; false: not registered"),
):
    """Every child in a Bal Panchayat, boys included (members are kept on the group)."""
    match: dict = {**group_scope(user, village_id), "group_type": "bal_panchayat"}
    if group_id:
        match["_id"] = oid(group_id)
    child: dict = {}
    if q:
        child["members.name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    if registered is not None:
        child["members.girl_id"] = {"$ne": None} if registered else None
    rows = await (await db[c.GROUPS].aggregate([
        {"$match": match},
        {"$unwind": "$members"},
        {"$match": child},
        {"$sort": {"village_id": 1, "name": 1, "members.name": 1}},
        {"$facet": {
            "total": [{"$count": "n"}],
            "items": [{"$skip": (pg.page - 1) * pg.page_size}, {"$limit": pg.page_size},
                      {"$project": {"member": "$members", "group_id": "$_id", "group_name": "$name",
                                    "group_name_en": "$name_en", "village_id": 1}}],
        }},
    ])).to_list()
    data = rows[0] if rows else {"total": [], "items": []}
    villages = {v["_id"]: v for v in await db[c.VILLAGES].find(
        {"_id": {"$in": list({r["village_id"] for r in data["items"]})}}, {"name": 1, "name_mr": 1}).to_list()}
    items = [{**serialize(r["member"]), "name_en": to_latin(r["member"].get("name")),
              "group": {"id": str(r["group_id"]), "name": r["group_name"], "name_en": r.get("group_name_en")},
              "village": serialize(villages.get(r["village_id"]))} for r in data["items"]]
    return {"items": items, "total": data["total"][0]["n"] if data["total"] else 0, "page": pg.page, "page_size": pg.page_size}


@router.get("/groups/{group_id}")
async def get_group(group_id: str, db: Db, user: CurrentUser):
    group = await get_or_404(db[c.GROUPS], group_id, "Group", group_scope(user))
    girls = await db[c.GIRLS].find(
        {"$or": [{"group_id": group["_id"]}, {"bal_panchayat_id": group["_id"]}], "is_deleted": {"$ne": True}},
        {"girl_code": 1, "name": 1, "name_en": 1, "name_mr": 1, "dob": 1, "age": 1},
    ).sort("girl_code", 1).to_list()
    # Bal Panchayat lists include boys, who are not registered beneficiaries; every child is kept as a member.
    members = group.get("members", [])
    return {**serialize(group), "girls": serialize(girls), "girl_count": len(girls), "member_count": len(members)}


@router.patch("/groups/{group_id}")
async def update_group(group_id: str, body: GroupUpdate, db: Db, actor: Stakeholder):
    from app.core.deps import check_not_read_only
    check_not_read_only(actor)
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
