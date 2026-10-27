"""Event management (PRD 4.6)."""

from collections import defaultdict
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.core.deps import Db, Pagination, Stakeholder, can_access_village, require_permission, user_village_ids, village_scope, narrow_to_village
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.beneficiaries import ApprovalDecision
from app.schemas.events import (
    AttendanceUpdate,
    CancelRequest,
    ChecklistUpdate,
    EventCreate,
    EventReport,
    EventUpdate,
    ExpenditureUpdate,
)
from app.services import audit, exporters, notifications, storage
from app.services.beneficiaries import touch_participation
from app.services.events import (
    DEFAULT_POST_CHECKLIST,
    DEFAULT_PRE_CHECKLIST,
    display_status,
    event_window,
    local_day_bounds,
    remind_participants,
    status_query,
    summarize_attendance,
)
from app.services.lookups import ensure_code, get_lookup
from app.services.validation import validate_entity
from app.utils.dates import local_tz, today_local, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, oids, serialize

router = APIRouter(prefix="/events", tags=["events"])
DisplayStatus = Literal["upcoming", "today", "overdue", "completed", "cancelled"]


def event_out(ev: dict, full: bool = False) -> dict:
    out = serialize(ev)
    out["display_status"] = display_status(ev)
    out["attendance_summary"] = summarize_attendance(ev)
    out["local_date"] = ev["start_at"].astimezone(local_tz()).date().isoformat()
    if not full:
        out.pop("attendance", None)
    return out


async def _responsible(db, volunteer_id, village_id):
    if not volunteer_id:
        return None
    vol = await db[c.USERS].find_one({"_id": oid(volunteer_id), "role": Role.VOLUNTEER.value, "is_active": True})
    if not vol:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Responsible volunteer not found or inactive")
    if not can_access_village(vol, village_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Responsible Volunteer must be assigned to the event's village")
    return vol


async def _groups(db, group_ids, village_id):
    ids = oids(group_ids)
    if ids and await db[c.GROUPS].count_documents({
        "_id": {"$in": ids},
        "$or": [{"village_id": village_id}, {"member_village_ids": village_id}],
    }) != len(set(ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invited groups must belong to the event's village")
    return list(dict.fromkeys(ids))


def _checklist(items: list[str]) -> list[dict]:
    return [{"item": i, "done": False, "notes": None, "done_at": None, "done_by": None} for i in items]


async def _load(db, event_id: str, user: dict) -> dict:
    return await get_or_404(db[c.EVENTS], event_id, "Event", {"is_deleted": {"$ne": True}, **village_scope(user)})


def _require_open(ev: dict):
    if ev["status"] == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is cancelled")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(body: EventCreate, db: Db, actor: Stakeholder):
    from app.core.deps import check_not_read_only
    check_not_read_only(actor)
    village = await get_or_404(db[c.VILLAGES], body.village_id, "Village")
    await ensure_code(db, "event_type", body.event_type, "event_type")
    vol = await _responsible(db, body.responsible_volunteer_id, village["_id"])
    groups = await _groups(db, body.group_ids, village["_id"])
    start_at, end_at = event_window(body.event_date, body.start_time, body.end_time)
    if not body.is_historical and body.event_date < today_local():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Event date is in the past. Set is_historical=true to back-date a past event.")
    if body.is_historical and body.event_date > today_local():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Historical events cannot be future-dated")
    etype = await get_lookup(db, "event_type", body.event_type)
    attrs = (etype or {}).get("attributes", {})
    now = utcnow()
    doc = {
        "title": body.title,
        "event_type": body.event_type,
        "objective": body.objective,
        "village_id": village["_id"],
        "taluka_id": village["taluka_id"],
        "location_name": body.location_name,
        "location": body.location.model_dump() if body.location else village.get("location"),
        "start_at": start_at,
        "end_at": end_at,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "responsible_volunteer_id": vol["_id"] if vol else None,
        "expected_participants": body.expected_participants,
        "group_ids": groups,
        "status": "scheduled",
        "is_historical": body.is_historical,
        "planned": not body.is_historical,  # created in advance -> counts as "planned" in planned-vs-conducted
        "pre_checklist": _checklist(body.pre_checklist or attrs.get("pre_checklist") or DEFAULT_PRE_CHECKLIST),
        "post_checklist": _checklist(body.post_checklist or attrs.get("post_checklist") or DEFAULT_POST_CHECKLIST),
        "attendance": [],
        "other_participants": {},
        "report": None,
        "expenditure": {"items": [], "total": 0, "resources_used": []},
        "planned_budget": body.planned_budget,
        "notify_participants": body.notify_participants,
        "media_ids": [],
        "reschedule_history": [],
        "cancel_reason": None,
        "approval": {"status": "not_required", "by": None, "at": None, "remarks": None},
        "created_by": actor["_id"],
        "created_at": now,
        "updated_at": now,
    }
    await validate_entity(db, "event", doc)
    res = await db[c.EVENTS].insert_one(doc)
    if vol and not body.is_historical:
        await notifications.notify(db, vol["_id"], "event_assigned", f"New event: {body.title}",
                                   f"{body.event_date} {body.start_time} at {body.location_name or village['name']}",
                                   entity_type="event", entity_id=res.inserted_id)
    await audit.log(db, actor, "create", "event", res.inserted_id, f"Scheduled event '{body.title}' on {body.event_date}")
    return event_out(doc, full=True)


@router.get("")
async def list_events(
    db: Db,
    user: Annotated[dict, Depends(require_permission("events", "read"))],
    pg: Pagination,
    display: Annotated[DisplayStatus | None, Query(alias="status")] = None,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    event_type: str | None = None,
    responsible_volunteer_id: ObjectIdStr | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    query: dict = {"is_deleted": {"$ne": True}, **village_scope(user)}
    if display:
        query.update(status_query(display))
    narrow_to_village(query, user, village_id)
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if event_type:
        query["event_type"] = event_type
    if responsible_volunteer_id:
        query["responsible_volunteer_id"] = oid(responsible_volunteer_id)
    if start_date or end_date:
        s, e = local_day_bounds(start_date or date(2000, 1, 1), end_date or date(2100, 1, 1))
        query["start_at"] = {**query.get("start_at", {}), "$gte": s, "$lt": e}
    total = await db[c.EVENTS].count_documents(query)
    sort_dir = 1 if display in ("upcoming", "today") else -1
    docs = await db[c.EVENTS].find(query).sort("start_at", sort_dir) \
        .skip((pg.page - 1) * pg.page_size).limit(pg.page_size).to_list()
    return {"items": [event_out(d) for d in docs], "total": total, "page": pg.page, "page_size": pg.page_size}


@router.get("/calendar")
async def calendar(
    db: Db,
    user: Annotated[dict, Depends(require_permission("events", "read"))],
    start_date: date,
    end_date: date,
    village_id: ObjectIdStr | None = None,
    event_type: str | None = None,
):
    """Events grouped by local date, with upcoming/completed/cancelled/overdue status."""
    if (end_date - start_date).days > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Calendar range is limited to one year")
    s, e = local_day_bounds(start_date, end_date)
    query: dict = {"is_deleted": {"$ne": True}, "start_at": {"$gte": s, "$lt": e}, **village_scope(user)}
    narrow_to_village(query, user, village_id)
    if event_type:
        query["event_type"] = event_type
    docs = await db[c.EVENTS].find(query, {"attendance": 0}).sort("start_at", 1).to_list()
    villages = {v["_id"]: v["name"] for v in await db[c.VILLAGES].find({}, {"name": 1}).to_list()}
    days: dict = defaultdict(list)
    counts: dict = defaultdict(int)
    for d in docs:
        out = event_out(d)
        out["village_name"] = villages.get(d["village_id"])
        days[out["local_date"]].append(out)
        counts[out["display_status"]] += 1
    return {"start_date": start_date, "end_date": end_date, "counts": counts,
            "days": [{"date": k, "events": v} for k, v in sorted(days.items())]}


@router.get("/planned-vs-conducted")
async def planned_vs_conducted(
    db: Db,
    _: Stakeholder,
    start_date: date,
    end_date: date,
    group_by: Literal["event_type", "village", "month", "volunteer"] = "event_type",
    taluka_id: ObjectIdStr | None = None,
):
    s, e = local_day_bounds(start_date, end_date)
    match: dict = {"start_at": {"$gte": s, "$lt": e}}
    if taluka_id:
        match["taluka_id"] = oid(taluka_id)
    key = {
        "event_type": "$event_type",
        "village": "$village_id",
        "volunteer": "$responsible_volunteer_id",
        "month": {"$dateToString": {"format": "%Y-%m", "date": "$start_at", "timezone": str(local_tz())}},
    }[group_by]
    now = utcnow()
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": key,
            "planned": {"$sum": {"$cond": ["$planned", 1, 0]}},
            "conducted": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "conducted_as_planned": {"$sum": {"$cond": [{"$and": ["$planned", {"$eq": ["$status", "completed"]}]}, 1, 0]}},
            "unplanned_conducted": {"$sum": {"$cond": [{"$and": [{"$not": ["$planned"]}, {"$eq": ["$status", "completed"]}]}, 1, 0]}},
            "cancelled": {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}},
            "overdue": {"$sum": {"$cond": [{"$and": [{"$eq": ["$status", "scheduled"]}, {"$lt": ["$end_at", now]}]}, 1, 0]}},
            "upcoming": {"$sum": {"$cond": [{"$and": [{"$eq": ["$status", "scheduled"]}, {"$gte": ["$end_at", now]}]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = [r async for r in await db[c.EVENTS].aggregate(pipeline)]
    labels: dict = {}
    if group_by == "village":
        labels = {v["_id"]: v["name"] for v in await db[c.VILLAGES].find({}, {"name": 1}).to_list()}
    elif group_by == "volunteer":
        labels = {u["_id"]: u["name"] for u in await db[c.USERS].find({"role": "volunteer"}, {"name": 1}).to_list()}
    elif group_by == "event_type":
        labels = {lk["code"]: lk["label"] for lk in await db[c.LOOKUPS].find({"type": "event_type"}).to_list()}
    out = []
    for r in rows:
        planned = r["planned"]
        out.append({
            "key": serialize(r["_id"]),
            "label": labels.get(r["_id"], r["_id"] if isinstance(r["_id"], str) else "Unassigned"),
            **{k: v for k, v in r.items() if k != "_id"},
            "completion_rate": round(r["conducted_as_planned"] / planned, 2) if planned else None,
        })
    totals = {k: sum(x[k] for x in out) for k in ("planned", "conducted", "conducted_as_planned",
                                                    "unplanned_conducted", "cancelled", "overdue", "upcoming")}
    totals["completion_rate"] = round(totals["conducted_as_planned"] / totals["planned"], 2) if totals["planned"] else None
    return {"group_by": group_by, "start_date": start_date, "end_date": end_date, "rows": out, "totals": totals}


@router.get("/{event_id}")
async def get_event(event_id: str, db: Db, user: Annotated[dict, Depends(require_permission("events", "read"))]):
    ev = await _load(db, event_id, user)
    out = event_out(ev, full=True)
    girl_ids = [a["girl_id"] for a in ev.get("attendance", [])]
    girls = {g["_id"]: g for g in await db[c.GIRLS].find({"_id": {"$in": girl_ids}}, {"girl_code": 1, "name": 1, "name_en": 1, "group_id": 1}).to_list()}
    for a in out["attendance"]:
        g = girls.get(oid(a["girl_id"]))
        a["girl_code"] = g["girl_code"] if g else None
        a["name"] = g.get("name") if g else None
        a["name_en"] = g.get("name_en") if g else None
    out["village"] = serialize(await db[c.VILLAGES].find_one({"_id": ev["village_id"]}, {"name": 1, "name_mr": 1}))
    out["groups"] = serialize(await db[c.GROUPS].find({"_id": {"$in": ev.get("group_ids", [])}}, {"name": 1, "name_en": 1}).to_list())
    if ev.get("responsible_volunteer_id"):
        out["responsible_volunteer"] = serialize(
            await db[c.USERS].find_one({"_id": ev["responsible_volunteer_id"]}, {"name": 1, "phone": 1}))
    out["media"] = serialize(await db[c.MEDIA].find({"entity_type": "event", "entity_id": ev["_id"]}).to_list())
    return out


@router.patch("/{event_id}")
async def update_event(event_id: str, body: EventUpdate, db: Db, actor: Stakeholder):
    from app.core.deps import check_not_read_only
    check_not_read_only(actor)
    before = await _load(db, event_id, actor)
    _require_open(before)
    updates = body.model_dump(exclude_unset=True, exclude={"reschedule_reason"})
    if not updates:
        return event_out(before, full=True)
    if "event_type" in updates:
        await ensure_code(db, "event_type", updates["event_type"], "event_type")
    if "responsible_volunteer_id" in updates:
        vol = await _responsible(db, updates["responsible_volunteer_id"], before["village_id"])
        updates["responsible_volunteer_id"] = vol["_id"] if vol else None
    if "group_ids" in updates:
        updates["group_ids"] = await _groups(db, updates["group_ids"], before["village_id"])
    if updates.get("location") is not None:
        updates["location"] = body.location.model_dump()
    push: dict = {}
    if {"event_date", "start_time", "end_time"} & updates.keys():
        local = before["start_at"].astimezone(local_tz())
        d = updates.pop("event_date", None) or local.date()
        st = updates.get("start_time") or before.get("start_time") or local.strftime("%H:%M")
        et = updates.get("end_time", before.get("end_time"))
        start_at, end_at = event_window(d, st, et)
        if before["status"] == "scheduled" and start_at.astimezone(local_tz()).date() < today_local() and not before.get("is_historical"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cannot reschedule an upcoming event into the past")
        updates.update(start_at=start_at, end_at=end_at)
        push["reschedule_history"] = {"from": before["start_at"], "to": start_at, "by": actor["_id"],
                                      "at": utcnow(), "reason": body.reschedule_reason}
    updates["updated_at"] = utcnow()
    op: dict = {"$set": updates}
    if push:
        op["$push"] = push
    await db[c.EVENTS].update_one({"_id": before["_id"]}, op)
    after = await db[c.EVENTS].find_one({"_id": before["_id"]})
    changes = diff(before, after, ["title", "event_type", "objective", "location_name", "start_at", "end_at",
                                   "responsible_volunteer_id", "expected_participants", "group_ids", "planned_budget",
                                   "notify_participants"])
    if push and after.get("responsible_volunteer_id"):
        await notifications.notify(db, after["responsible_volunteer_id"], "event_rescheduled",
                                   f"Event rescheduled: {after['title']}", body.reschedule_reason or "",
                                   entity_type="event", entity_id=after["_id"])
    await audit.log(db, actor, "update", "event", before["_id"], f"Updated event '{after['title']}'", changes)
    return event_out(after, full=True)


@router.post("/{event_id}/cancel")
async def cancel_event(event_id: str, body: CancelRequest, db: Db, actor: Stakeholder):
    from app.core.deps import check_can_delete
    check_can_delete(actor)
    ev = await _load(db, event_id, actor)
    if ev["status"] != "scheduled":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only scheduled events can be cancelled (event is {ev['status']})")
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": {
        "status": "cancelled", "cancel_reason": body.reason, "cancelled_by": actor["_id"],
        "cancelled_at": utcnow(), "updated_at": utcnow()}})
    if ev.get("responsible_volunteer_id"):
        await notifications.notify(db, ev["responsible_volunteer_id"], "event_cancelled",
                                   f"Event cancelled: {ev['title']}", body.reason, entity_type="event", entity_id=ev["_id"])
    await audit.log(db, actor, "status_change", "event", ev["_id"], f"Cancelled event '{ev['title']}'",
                    {"status": {"from": "scheduled", "to": "cancelled"}}, {"reason": body.reason})
    return event_out(await db[c.EVENTS].find_one({"_id": ev["_id"]}), full=True)


@router.put("/{event_id}/checklists/{which}")
async def update_checklist(event_id: str, which: Literal["pre", "post"], body: ChecklistUpdate, db: Db,
                           user: Annotated[dict, Depends(require_permission("events", "update"))]):
    ev = await _load(db, event_id, user)
    _require_open(ev)
    field = f"{which}_checklist"
    previous = {i["item"]: i for i in ev.get(field, [])}
    now = utcnow()
    items = []
    for it in body.items:
        prev = previous.get(it.item, {})
        became_done = it.done and not prev.get("done")
        items.append({
            "item": it.item, "done": it.done, "notes": it.notes,
            "done_at": now if became_done else (prev.get("done_at") if it.done else None),
            "done_by": user["_id"] if became_done else (prev.get("done_by") if it.done else None),
        })
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": {field: items, "updated_at": now}})
    await audit.log(db, user, "update", "event", ev["_id"], f"Updated {which}-event checklist")
    return event_out(await db[c.EVENTS].find_one({"_id": ev["_id"]}), full=True)


@router.put("/{event_id}/attendance")
async def update_attendance(event_id: str, body: AttendanceUpdate, db: Db,
                            user: Annotated[dict, Depends(require_permission("events", "update"))]):
    ev = await _load(db, event_id, user)
    _require_open(ev)
    if ev["start_at"] > utcnow():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Attendance can only be captured once the event has started")
    now = utcnow()
    current = {} if body.replace else {a["girl_id"]: a for a in ev.get("attendance", [])}

    requested = {oid(e.girl_id): e.present for e in body.entries}
    group_ids = await _groups(db, body.mark_groups_present, ev["village_id"])
    if group_ids:
        async for g in db[c.GIRLS].find({
            "$or": [{"group_id": {"$in": group_ids}}, {"bal_panchayat_id": {"$in": group_ids}}],
            "is_deleted": {"$ne": True},
        }, {"_id": 1}):
            requested.setdefault(g["_id"], True)
    if requested:
        girls = {g["_id"]: g async for g in db[c.GIRLS].find(
            {"_id": {"$in": list(requested)}, "is_deleted": {"$ne": True}}, {"group_id": 1, "village_id": 1})}
        missing = set(requested) - set(girls)
        if missing:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown girl ids: {[str(m) for m in missing]}")
        wrong_village = [str(gid) for gid in requested if girls[gid].get("village_id") != ev["village_id"]]
        if wrong_village:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Attendance can only include girls from the event's village")
        for gid, present in requested.items():
            current[gid] = {"girl_id": gid, "group_id": girls[gid].get("group_id"), "present": present,
                            "marked_at": now, "marked_by": user["_id"]}
    sets: dict = {"attendance": list(current.values()), "updated_at": now}
    if body.other_participants:
        sets["other_participants"] = body.other_participants.model_dump()
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": sets})
    present_ids = [a["girl_id"] for a in current.values() if a["present"]]
    await touch_participation(db, present_ids, ev["start_at"])
    await audit.log(db, user, "update", "event", ev["_id"], f"Attendance updated ({len(present_ids)} present)")
    return event_out(await db[c.EVENTS].find_one({"_id": ev["_id"]}), full=True)


@router.post("/{event_id}/report")
async def submit_report(event_id: str, body: EventReport, db: Db,
                        user: Annotated[dict, Depends(require_permission("events", "update"))]):
    ev = await _load(db, event_id, user)
    _require_open(ev)
    if ev["start_at"] > utcnow():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A report cannot be submitted before the event starts")
    now = utcnow()
    report = {**body.model_dump(), "attendance": summarize_attendance(ev), "submitted_by": user["_id"],
              "submitted_at": (ev.get("report") or {}).get("submitted_at") or now, "last_edited_at": now}
    sets = {"report": report, "status": "completed", "completed_at": ev.get("completed_at") or now, "updated_at": now}
    if user["role"] == Role.VOLUNTEER:
        sets["approval"] = {"status": "pending", "by": None, "at": None, "remarks": None}
    # Tick the matching post-event checklist item automatically.
    post = ev.get("post_checklist", [])
    for item in post:
        if item["item"].lower().startswith("post-event report") and not item["done"]:
            item.update(done=True, done_at=now, done_by=user["_id"])
    sets["post_checklist"] = post
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": sets})
    action = "update" if ev.get("report") else "create"
    await audit.log(db, user, action, "event_report", ev["_id"], f"{'Edited' if ev.get('report') else 'Submitted'} report for '{ev['title']}'")
    return event_out(await db[c.EVENTS].find_one({"_id": ev["_id"]}), full=True)


@router.put("/{event_id}/expenditure")
async def update_expenditure(event_id: str, body: ExpenditureUpdate, db: Db,
                             actor: Annotated[dict, Depends(require_permission("events", "update"))]):
    ev = await _load(db, event_id, actor)
    _require_open(ev)
    items = [{**i.model_dump(), "amount": round(i.quantity * i.unit_cost, 2)} for i in body.items]
    total = round(sum(i["amount"] for i in items), 2)
    exp = {"items": items, "total": total, "resources_used": body.resources_used}
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": {"expenditure": exp, "updated_at": utcnow()}})
    await audit.log(db, actor, "update", "event", ev["_id"], f"Expenditure updated (total {total})",
                    {"expenditure_total": {"from": (ev.get("expenditure") or {}).get("total"), "to": total}})
    return event_out(await db[c.EVENTS].find_one({"_id": ev["_id"]}), full=True)


@router.post("/{event_id}/media", status_code=status.HTTP_201_CREATED)
async def upload_event_media(
    event_id: str,
    db: Db,
    user: Annotated[dict, Depends(require_permission("events", "update"))],
    file: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    accuracy_m: float | None = Form(None),
    captured_at: datetime | None = Form(None),
    caption: str | None = Form(None),
):
    ev = await _load(db, event_id, user)
    _require_open(ev)
    doc, created = await storage.save_upload(db, file, "event", ev["_id"], user, lat=lat, lng=lng,
                                             accuracy_m=accuracy_m, captured_at=captured_at, caption=caption)
    if created:
        await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$addToSet": {"media_ids": doc["_id"]}})
        await audit.log(db, user, "create", "media", doc["_id"], f"Uploaded media to event '{ev['title']}'")
    return {**serialize(doc), "duplicate": not created}


@router.post("/{event_id}/notify-participants")
async def notify_participants(event_id: str, db: Db, actor: Stakeholder):
    """Send the SMS reminder to invited girls' families now (each phone number only once per event)."""
    ev = await _load(db, event_id, actor)
    if ev["status"] != "scheduled" or ev["end_at"] < utcnow():
        raise HTTPException(status.HTTP_409_CONFLICT, "Reminders can only be sent for upcoming events")
    if not ev.get("group_ids"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The event has no invited groups")
    counts = await remind_participants(db, ev, actor)
    await audit.log(db, actor, "create", "message", ev["_id"], f"Participant reminders for '{ev['title']}'", meta=counts)
    return counts


@router.post("/{event_id}/approval")
async def approve_event_report(event_id: str, body: ApprovalDecision, db: Db, actor: Stakeholder):
    ev = await _load(db, event_id, actor)
    if not ev.get("report"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Event has no report to approve")
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": {"approval": {
        "status": body.decision, "by": actor["_id"], "at": utcnow(), "remarks": body.remarks}}})
    await audit.log(db, actor, "approve" if body.decision == "approved" else "reject", "event_report", ev["_id"],
                    f"{body.decision.title()} report for '{ev['title']}'", meta={"remarks": body.remarks})
    return event_out(await db[c.EVENTS].find_one({"_id": ev["_id"]}), full=True)


@router.get("/{event_id}/export")
async def export_event_report(event_id: str, db: Db, user: Annotated[dict, Depends(require_permission("events", "read"))],
                              format: Literal["pdf", "xlsx"] = "pdf"):
    """Event report as PDF or Excel."""
    ev = await get_event(event_id, db, user)
    content, media_type, ext = exporters.event_report(ev, format)
    filename = f"event-{ev['local_date']}-{ev['id'][-6:]}.{ext}"
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})



@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: str, db: Db, actor: Stakeholder, reason: str = Query("Deleted by Super Admin")):
    from app.core.deps import check_can_delete
    check_can_delete(actor)
    ev = await get_or_404(db[c.EVENTS], event_id, "Event", {"is_deleted": {"$ne": True}})
    now = utcnow()
    await db[c.EVENTS].update_one(
        {"_id": ev["_id"]},
        {"$set": {
            "is_deleted": True,
            "status": "cancelled",
            "deleted_at": now,
            "deleted_by": actor["_id"],
            "delete_reason": reason,
        }}
    )
    await audit.log(db, actor, "delete", "event", ev["_id"], f"Deleted event {ev.get('title')}", meta={"reason": reason})
