"""Event management (PRD 4.6)."""

from collections import defaultdict
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.deps import ADMIN_ROLES, CurrentUser, Db, Pagination, Stakeholder, can_access_village, require_permission, user_village_ids, village_scope, narrow_to_village
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
    MEETING_EVENT_TYPES,
    display_status,
    event_window,
    groups_pending,
    local_day_bounds,
    meeting_event_doc,
    month_bounds_utc,
    monthly_planner_rows,
    remind_participants,
    status_query,
    summarize_attendance,
)
from app.services.lookups import ensure_code, get_lookup
from app.services.validation import validate_entity
from app.utils.dates import local_tz, today_local, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, oids, serialize

router = APIRouter(prefix="/events", tags=["events"])
DisplayStatus = Literal["upcoming", "today", "ongoing", "overdue", "completed", "cancelled"]


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
async def create_event(body: EventCreate, db: Db, actor: CurrentUser):
    from app.core.deps import check_not_read_only
    is_volunteer = actor.get("role") == Role.VOLUNTEER.value
    if not is_volunteer and actor.get("role") not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to create events")
    check_not_read_only(actor)
    village = await get_or_404(db[c.VILLAGES], body.village_id, "Village")
    if is_volunteer:
        # Volunteers may only schedule events in their own villages, and are always the responsible volunteer.
        if not can_access_village(actor, village["_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only create events in your assigned villages")
        body.responsible_volunteer_id = str(actor["_id"])
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
    if vol and not body.is_historical and vol["_id"] != actor["_id"]:
        await notifications.notify(db, vol["_id"], "event_assigned", f"New event: {body.title}",
                                   f"{body.event_date} {body.start_time} at {body.location_name or village['name']}",
                                   entity_type="event", entity_id=res.inserted_id)
    await audit.log(db, actor, "create", "event", res.inserted_id, f"Scheduled event '{body.title}' on {body.event_date}")
    return event_out(doc, full=True)


class PlannedMeeting(BaseModel):
    group_id: ObjectIdStr
    meeting_date: date
    start_time: str = Field("10:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    responsible_volunteer_id: ObjectIdStr | None = None


class MonthlyPlan(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    meetings: list[PlannedMeeting] = Field(min_length=1, max_length=1000)


@router.get("/monthly-planner")
async def get_monthly_planner(
    db: Db,
    _: Stakeholder,
    year: int | None = Query(None, ge=2000, le=2100, description="Year (default: current year)"),
    month: int | None = Query(None, ge=1, le=12, description="Month (default: current month)"),
):
    """Kishori / Bal Panchayat groups for the monthly meeting planner, with a suggested slot per group
    and any meeting already scheduled that month. Nothing is created here."""
    today = today_local()
    year, month = year or today.year, month or today.month
    rows = await monthly_planner_rows(db, year, month)
    return {"year": year, "month": month, "today": today.isoformat(), "groups": rows,
            "already_planned": sum(1 for r in rows if r["existing_event_id"])}


@router.post("/monthly-planner")
async def create_monthly_plan(body: MonthlyPlan, db: Db, actor: Stakeholder):
    """Create the monthly meetings the admin picked in the planner (one per group, skipping groups
    that already have that month's meeting)."""
    from app.core.deps import check_not_read_only
    check_not_read_only(actor)
    today = today_local()
    s_utc, e_utc = month_bounds_utc(body.year, body.month)
    group_ids = [oid(m.group_id) for m in body.meetings]
    if len(set(group_ids)) != len(group_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Each group can have only one meeting in the plan")
    groups = {g["_id"]: g for g in await db[c.GROUPS].find({
        "_id": {"$in": group_ids}, "group_type": {"$in": list(MEETING_EVENT_TYPES)},
        "is_active": True, "is_deleted": {"$ne": True}}).to_list()}
    errors = []
    for m in body.meetings:
        if oid(m.group_id) not in groups:
            errors.append(f"Group {m.group_id} is not an active Kishori / Bal Panchayat group")
        elif (m.meeting_date.year, m.meeting_date.month) != (body.year, body.month):
            errors.append(f"{groups[oid(m.group_id)]['name']}: date must be in {body.year}-{body.month:02d}")
        elif m.meeting_date < today:
            errors.append(f"{groups[oid(m.group_id)]['name']}: date is in the past")
        elif m.end_time and m.end_time <= m.start_time:
            errors.append(f"{groups[oid(m.group_id)]['name']}: end time must be after start time")
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(errors))

    created, skipped = [], []
    for m in body.meetings:
        g = groups[oid(m.group_id)]
        etype = MEETING_EVENT_TYPES[g["group_type"]]
        if await db[c.EVENTS].find_one({"group_ids": g["_id"], "event_type": etype, "is_deleted": {"$ne": True},
                                        "start_at": {"$gte": s_utc, "$lt": e_utc}}, {"_id": 1}):
            skipped.append({"group_id": str(g["_id"]), "group_name": g.get("name"), "reason": "already planned"})
            continue
        vol = None
        if m.responsible_volunteer_id:
            vol = await db[c.USERS].find_one({"_id": oid(m.responsible_volunteer_id), "role": "volunteer", "is_active": True})
            if not vol:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    f"{g.get('name')}: responsible volunteer not found")
        vol_id = vol["_id"] if vol else g.get("responsible_volunteer_id")
        doc = meeting_event_doc(g, m.meeting_date, m.start_time, m.end_time, vol_id, actor["_id"], body.year, body.month)
        res = await db[c.EVENTS].insert_one(doc)
        created.append({"id": str(res.inserted_id), "group_id": str(g["_id"]), "title": doc["title"],
                        "start_at": doc["start_at"].isoformat()})
        if vol_id and vol_id != actor["_id"]:
            await notifications.notify(db, vol_id, "event_assigned", f"New event: {doc['title']}",
                                       f"{m.meeting_date.isoformat()} {m.start_time} at {doc['location_name']}",
                                       entity_type="event", entity_id=res.inserted_id)
    await audit.log(db, actor, "create", "event", None,
                    f"Planned {len(created)} monthly meetings for {body.year}-{body.month:02d}",
                    meta={"created": len(created), "skipped": len(skipped)})
    return {"created": len(created), "skipped": skipped, "events": created}


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
    # Same date order for every filter. Many events share a start time, so title and _id break
    # the tie and keep pages stable (no event repeated or skipped between pages).
    docs = await db[c.EVENTS].find(query).sort([("start_at", 1), ("title", 1), ("_id", 1)]) \
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
    docs = await db[c.EVENTS].find(query, {"attendance": 0}).sort([("start_at", 1), ("title", 1), ("_id", 1)]).to_list()
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


class GroupsDone(BaseModel):
    group_ids: list[ObjectIdStr] = Field(default_factory=list, description="Groups whose meeting is done")


@router.put("/{event_id}/groups-done")
async def update_groups_done(event_id: str, body: GroupsDone, db: Db,
                             user: Annotated[dict, Depends(require_permission("events", "update"))]):
    """Mark which groups of a village meeting have held their meeting. The meeting stays ongoing
    until every group is done, then completes on its own."""
    ev = await _load(db, event_id, user)
    _require_open(ev)
    if not ev.get("track_groups"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This event does not track groups")
    ids = list(dict.fromkeys(oids(body.group_ids)))
    if set(ids) - set(ev.get("group_ids") or []):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only the meeting's own groups can be marked done")
    now = utcnow()
    previous = {g["group_id"]: g for g in ev.get("groups_done") or []}
    done = [previous.get(gid) or {"group_id": gid, "done_at": now, "done_by": user["_id"]} for gid in ids]
    sets: dict = {"groups_done": done, "updated_at": now}
    all_done = not groups_pending({**ev, "groups_done": done})
    if all_done and ev["status"] == "scheduled":
        sets.update(status="completed", completed_at=now)
    elif not all_done and ev["status"] == "completed" and not ev.get("report"):
        sets.update(status="scheduled", completed_at=None)
    await db[c.EVENTS].update_one({"_id": ev["_id"]}, {"$set": sets})
    await audit.log(db, user, "update", "event", ev["_id"],
                    f"Groups done: {len(done)}/{len(ev.get('group_ids') or [])}")
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
    if ev.get("track_groups") and groups_pending(ev):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Mark every group's meeting as done before submitting the report")
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
