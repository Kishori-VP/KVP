"""Target management (PRD 4.8)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import Db, Pagination, Stakeholder, require_permission, user_village_ids
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.targets import TargetCancel, TargetCreate, TargetRevise
from app.services import audit, notifications
from app.services.lookups import get_lookup
from app.services.targets import TARGET_STATUSES, with_progress
from app.utils.dates import next_period, period_bounds, to_date, to_dt, today_local, utcnow
from app.utils.mongo import ObjectIdStr, get_or_404, oid, oids, serialize

router = APIRouter(prefix="/targets", tags=["targets"])


def _periods(body: TargetCreate) -> list[tuple[date, date]]:
    if body.period_type == "custom":
        return [(body.period_start, body.period_end)]
    first = period_bounds(body.period_type, body.reference_date or body.period_start or today_local())
    out = [first]
    while len(out) < body.periods:
        out.append(next_period(body.period_type, out[-1][1]))
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_targets(body: TargetCreate, db: Db, actor: Stakeholder):
    ttype = await get_lookup(db, "target_type", body.target_type)
    if not ttype or not ttype.get("is_active"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown target type '{body.target_type}'")
    metric = ttype.get("attributes", {}).get("metric")
    vq: dict = {"role": Role.VOLUNTEER.value, "is_active": True}
    if not body.all_active_volunteers:
        vq["_id"] = {"$in": oids(body.volunteer_ids)}
    volunteers = await db[c.USERS].find(vq).to_list()
    if not body.all_active_volunteers and len(volunteers) != len(set(body.volunteer_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Some volunteers were not found or are inactive")
    no_village = [v["name"] for v in volunteers if not v.get("village_id")]
    if no_village:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Volunteers without a village: {no_village}")

    periods = _periods(body)
    if periods[-1][1] < today_local() and body.period_type != "custom":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Target period has already ended")
    now = utcnow()
    created, skipped = [], []
    for vol in volunteers:
        for start, end in periods:
            clash = await db[c.TARGETS].find_one({
                "volunteer_id": vol["_id"], "target_type": body.target_type, "status": "active",
                "period_start": {"$lte": to_dt(end)}, "period_end": {"$gte": to_dt(start)},
            })
            if clash:
                skipped.append({"volunteer": vol["name"], "period_start": start, "period_end": end,
                                "reason": "An overlapping active target of this type exists"})
                continue
            doc = {
                "volunteer_id": vol["_id"],
                # One combined target across all of the volunteer's villages (village_id None means "all").
                "village_id": None,
                "village_ids": user_village_ids(vol),
                "taluka_id": vol.get("taluka_id"),
                "target_type": body.target_type,
                "metric": metric,
                "title": body.title or ttype["label"],
                "notes": body.notes,
                "period_type": body.period_type,
                "period_start": to_dt(start),
                "period_end": to_dt(end),
                "target_value": body.target_value,
                "original_value": body.target_value,
                "status": "active",
                "revisions": [],
                "created_by": actor["_id"],
                "created_at": now,
                "updated_at": now,
            }
            res = await db[c.TARGETS].insert_one(doc)
            created.append(doc)
            await audit.log(db, actor, "create", "target", res.inserted_id,
                            f"{ttype['label']} target {body.target_value} for {vol['name']} ({start} to {end})")
        if any(t["volunteer_id"] == vol["_id"] for t in created):
            await notifications.notify(db, vol["_id"], "target_assigned", f"New target: {body.title or ttype['label']}",
                                       f"{body.target_value} ({body.period_type}) from {periods[0][0]}",
                                       entity_type="target")
    return {"created": serialize(created), "skipped": serialize(skipped)}


@router.get("")
async def list_targets(
    db: Db,
    user: Annotated[dict, Depends(require_permission("targets", "read"))],
    pg: Pagination,
    volunteer_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    target_type: str | None = None,
    period_type: str | None = None,
    when: Literal["current", "upcoming", "past", "all"] = "current",
    on_date: date | None = Query(None, description="Targets whose period includes this date"),
    status_: Annotated[str | None, Query(alias="status", description=f"One of {TARGET_STATUSES}")] = None,
):
    # Targets belong to the volunteer (combined across her villages), so volunteers see their own.
    query: dict = {}
    if user["role"] == Role.VOLUNTEER:
        query["volunteer_id"] = user["_id"]
    elif volunteer_id:
        query["volunteer_id"] = oid(volunteer_id)
    if village_id and user["role"] == Role.STAKEHOLDER:
        query["$or"] = [{"village_id": oid(village_id)}, {"village_ids": oid(village_id)}]
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if target_type:
        query["target_type"] = target_type
    if period_type:
        query["period_type"] = period_type
    today = to_dt(on_date or today_local())
    if on_date or when == "current":
        query.update(period_start={"$lte": today}, period_end={"$gte": today})
    elif when == "upcoming":
        query["period_start"] = {"$gt": today}
    elif when == "past":
        query["period_end"] = {"$lt": today}
    if status_ == "cancelled":
        query["status"] = "cancelled"
    elif status_ is None or status_ != "all":
        query.setdefault("status", "active")

    docs = await db[c.TARGETS].find(query).sort([("period_end", 1), ("volunteer_id", 1)]).to_list()
    enriched = await with_progress(db, docs)
    if status_ and status_ not in ("cancelled", "all"):
        enriched = [t for t in enriched if t["progress"]["status"] == status_]
    total = len(enriched)
    page = enriched[(pg.page - 1) * pg.page_size: pg.page * pg.page_size]
    names = {u["_id"]: u["name"] for u in await db[c.USERS].find(
        {"_id": {"$in": [t["volunteer_id"] for t in page]}}, {"name": 1}).to_list()}
    items = [{**serialize(t), "volunteer_name": names.get(t["volunteer_id"])} for t in page]
    by_status: dict = {}
    for t in enriched:
        by_status[t["progress"]["status"]] = by_status.get(t["progress"]["status"], 0) + 1
    return {"items": items, "total": total, "page": pg.page, "page_size": pg.page_size, "by_status": by_status}


@router.get("/{target_id}")
async def get_target(target_id: str, db: Db, user: Annotated[dict, Depends(require_permission("targets", "read"))]):
    t = await get_or_404(db[c.TARGETS], target_id, "Target")
    if user["role"] == Role.VOLUNTEER and t["volunteer_id"] != user["_id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    [enriched] = await with_progress(db, [t])
    vol = await db[c.USERS].find_one({"_id": t["volunteer_id"]}, {"name": 1, "phone": 1})
    return {**serialize(enriched), "volunteer": serialize(vol)}


@router.patch("/{target_id}")
async def revise_target(target_id: str, body: TargetRevise, db: Db, actor: Stakeholder):
    """Revise a target. Every revision is kept in the target's history and the audit log."""
    t = await get_or_404(db[c.TARGETS], target_id, "Target")
    if t["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only active targets can be revised")
    updates = body.model_dump(exclude_unset=True, exclude={"reason"})
    if "period_end" in updates:
        if updates["period_end"] < to_date(t["period_start"]):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "period_end cannot be before period_start")
        updates["period_end"] = to_dt(updates["period_end"])
    changes = {k: {"from": serialize(t.get(k)), "to": serialize(v)} for k, v in updates.items() if t.get(k) != v}
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nothing to change")
    now = utcnow()
    await db[c.TARGETS].update_one(
        {"_id": t["_id"]},
        {"$set": {**updates, "updated_at": now},
         "$push": {"revisions": {"at": now, "by": actor["_id"], "by_name": actor["name"], "reason": body.reason,
                                 "changes": changes}}},
    )
    await notifications.notify(db, t["volunteer_id"], "target_revised", f"Target revised: {t['title']}", body.reason,
                               entity_type="target", entity_id=t["_id"])
    await audit.log(db, actor, "revise", "target", t["_id"], f"Revised target '{t['title']}'", changes,
                    {"reason": body.reason})
    [enriched] = await with_progress(db, [await db[c.TARGETS].find_one({"_id": t["_id"]})])
    return serialize(enriched)


@router.post("/{target_id}/cancel")
async def cancel_target(target_id: str, body: TargetCancel, db: Db, actor: Stakeholder):
    t = await get_or_404(db[c.TARGETS], target_id, "Target")
    if t["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Target is not active")
    now = utcnow()
    await db[c.TARGETS].update_one(
        {"_id": t["_id"]},
        {"$set": {"status": "cancelled", "cancel_reason": body.reason, "updated_at": now},
         "$push": {"revisions": {"at": now, "by": actor["_id"], "by_name": actor["name"], "reason": body.reason,
                                 "changes": {"status": {"from": "active", "to": "cancelled"}}}}},
    )
    await audit.log(db, actor, "status_change", "target", t["_id"], f"Cancelled target '{t['title']}'",
                    {"status": {"from": "active", "to": "cancelled"}}, {"reason": body.reason})
    return serialize(await db[c.TARGETS].find_one({"_id": t["_id"]}))
