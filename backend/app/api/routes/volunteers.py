"""Volunteer management (PRD 4.7) and reassignment (PRD 4.1)."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, Db, Stakeholder, require_permission
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.users import AssignRequest, GroupAssignment, HandoverRequest, ReassignRequest
from app.services import activity, assignments, audit, metrics, notifications
from app.services.app_settings import get_setting
from app.services.beneficiaries import OPEN_CASE_STATUSES
from app.services.events import local_day_bounds
from app.services.targets import handle_reassignment, with_progress
from app.utils.dates import (
    day_range,
    local_tz,
    period_bounds,
    to_date,
    to_dt,
    today_local,
    utcnow,
)
from app.utils.mongo import ObjectIdStr, get_or_404, oid, oids, serialize

router = APIRouter(prefix="/volunteers", tags=["volunteers"])


async def _volunteer(db, volunteer_id: str) -> dict:
    return await get_or_404(db[c.USERS], volunteer_id, "Volunteer", {"role": Role.VOLUNTEER.value})


async def _names(db, coll, ids) -> dict:
    return {d["_id"]: d["name"] for d in await db[coll].find({"_id": {"$in": list(ids)}}, {"name": 1}).to_list()}


@router.get("")
async def list_volunteers(
    db: Db,
    _: Stakeholder,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    is_active: bool | None = True,
    assigned: bool | None = Query(None, description="true = has a village, false = not yet assigned"),
):
    query: dict = {"role": Role.VOLUNTEER.value}
    if assigned is True:
        query["$or"] = [{"village_id": {"$ne": None}}, {"village_ids": {"$exists": True, "$not": {"$size": 0}}}]
    elif assigned is False:
        query["village_id"] = None
        query["$or"] = [{"village_ids": None}, {"village_ids": {"$size": 0}}, {"village_ids": {"$exists": False}}]
    if village_id:
        vid = oid(village_id)
        query["$or"] = [{"village_id": vid}, {"village_ids": vid}]
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if is_active is not None:
        query["is_active"] = is_active
    vols = await db[c.USERS].find(query).sort("name", 1).to_list()
    villages = await _names(db, c.VILLAGES, {vid for v in vols for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else []))})
    groups = await _names(db, c.GROUPS, {g for v in vols for g in v.get("group_ids", [])})
    today = today_local()
    month_start, month_end = period_bounds("monthly", today)
    out = []
    for v in vols:
        open_cases = await db[c.CASES].count_documents({"assigned_to": v["_id"], "status": {"$in": OPEN_CASE_STATUSES}})
        visits = await metrics.home_visits(db, v["_id"], None, month_start, today)
        last_report = await db[c.ACTIVITY_REPORTS].find_one({"volunteer_id": v["_id"]}, sort=[("report_date", -1)])
        out.append({
            **serialize(v),
            "village_name": ", ".join(filter(None, [villages.get(vid) for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else []))])) or None,
            "village_names": [villages[vid] for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else [])) if vid in villages],
            "groups": [{"id": str(g), "name": groups.get(g)} for g in v.get("group_ids", [])],
            "home_visits_this_month": visits,
            "open_cases": open_cases,
            "last_report_date": last_report["report_date"].date() if last_report else None,
        })
    return out


@router.get("/performance")
async def performance(
    db: Db,
    _: Stakeholder,
    period: Literal["daily", "weekly", "monthly", "quarterly", "yearly"] = "monthly",
    reference_date: date | None = None,
    taluka_id: ObjectIdStr | None = None,
):
    """Volunteer-wise performance against targets for a period."""
    start, end = period_bounds(period, reference_date)
    vq: dict = {"role": Role.VOLUNTEER.value, "is_active": True}
    if taluka_id:
        vq["taluka_id"] = oid(taluka_id)
    vols = await db[c.USERS].find(vq).sort("name", 1).to_list()
    villages = await _names(db, c.VILLAGES, {vid for v in vols for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else []))})
    thresholds = await get_setting(db, "target_thresholds")
    rows = []
    for v in vols:
        targets = await db[c.TARGETS].find({
            "volunteer_id": v["_id"], "status": "active",
            "period_start": {"$lte": to_dt(end)}, "period_end": {"$gte": to_dt(start)},
        }).to_list()
        enriched = await with_progress(db, targets, thresholds)
        pcts = [min(t["progress"]["progress_pct"], 100) for t in enriched]
        summary = await metrics.activity_summary(db, v["_id"], v.get("village_id"), start, min(end, today_local()))
        rows.append({
            "volunteer_id": str(v["_id"]),
            "name": v["name"],
            "village_id": str(v["village_id"]) if v.get("village_id") else None,
            "village_name": ", ".join(filter(None, [villages.get(vid) for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else []))])) or None,
            "village_names": [villages[vid] for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else [])) if vid in villages],
            "activity": summary,
            "targets": [{"id": str(t["_id"]), "title": t["title"], "target_type": t["target_type"],
                         "target_value": t["target_value"], **t["progress"]} for t in enriched],
            "target_count": len(enriched),
            "avg_achievement_pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
            "targets_by_status": {s: sum(1 for t in enriched if t["progress"]["status"] == s)
                                  for s in ("on_track", "at_risk", "achieved", "missed", "upcoming")},
        })
    rows.sort(key=lambda r: -(r["avg_achievement_pct"] or -1))
    return {"period": period, "start": start, "end": end, "volunteers": rows}


@router.get("/submission-status")
async def submission_status(
    db: Db,
    _: Stakeholder,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Which volunteers have not submitted expected daily activity reports."""
    rules = await get_setting(db, "reporting")
    today = today_local()
    end = min(end_date or today - timedelta(days=rules["grace_days"]), today)
    start = start_date or end - timedelta(days=6)
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start_date is after the last reportable day")
    expected_days = activity.working_days(start, end, rules["working_days"]) \
        if rules["expected_activity_report"] == "daily" else []
    vols = await db[c.USERS].find({"role": Role.VOLUNTEER.value, "is_active": True, "village_id": {"$ne": None}})         .sort("name", 1).to_list()
    villages = await _names(db, c.VILLAGES, {vid for v in vols for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else []))})
    s, e = day_range(start, end)
    rows = []
    for v in vols:
        first = await db[c.VOLUNTEER_ASSIGNMENTS].find_one({"volunteer_id": v["_id"]}, sort=[("start_date", 1)])
        active_from = to_date(first["start_date"]) if first else to_date(v["created_at"])
        due = [d for d in expected_days if d >= active_from]
        submitted = {r["report_date"].date() async for r in db[c.ACTIVITY_REPORTS].find(
            {"volunteer_id": v["_id"], "report_date": {"$gte": s, "$lt": e}}, {"report_date": 1})}
        missing = [d for d in due if d not in submitted]
        pending_event_reports = await db[c.EVENTS].count_documents(
            {"responsible_volunteer_id": v["_id"], "status": "scheduled", "end_at": {"$lt": utcnow()}})
        rows.append({
            "volunteer_id": str(v["_id"]), "name": v["name"], "phone": v["phone"],
            "village_name": ", ".join(filter(None, [villages.get(vid) for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else []))])) or None,
            "village_names": [villages[vid] for vid in (v.get("village_ids") or ([v["village_id"]] if v.get("village_id") else [])) if vid in villages],
            "expected": len(due), "submitted": len([d for d in due if d in submitted]),
            "missing_dates": missing, "missing_count": len(missing),
            "submission_rate": round(1 - len(missing) / len(due), 2) if due else None,
            "pending_event_reports": pending_event_reports,
        })
    rows.sort(key=lambda r: -r["missing_count"])
    return {"start": start, "end": end, "expected_days": len(expected_days),
            "defaulters": sum(1 for r in rows if r["missing_count"] or r["pending_event_reports"]), "volunteers": rows}


@router.get("/me/dashboard")
async def my_dashboard(db: Db, user: CurrentUser, village_id: ObjectIdStr | None = None):
    """Tai home screen. Scoped to the selected village or all assigned villages."""
    if user.get("role") != Role.VOLUNTEER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tai access required")

    from app.core.deps import user_village_ids
    assigned_vids = user_village_ids(user)
    if not assigned_vids:
        return {"assigned": False, "user": {"id": str(user["_id"]), "name": user.get("name"), "role": user.get("role")}, "village": None, "villages": [], "summary": {},
                "targets": [], "upcoming_targets": [], "upcoming_events": [], "overdue_events": [], "upcoming_visits": [],
                "upcoming_cases": [], "overdue_case_items": [], "open_cases": 0, "overdue_cases": 0,
                "recent_visits": [], "recent_reports": [], "contacts": {}}
    await require_permission("dashboard", "read")(db, user)

    all_assigned_villages = await db[c.VILLAGES].find({"_id": {"$in": assigned_vids}}).sort("name", 1).to_list()
    active_vid = oid(village_id) if (village_id and oid(village_id) in assigned_vids) else assigned_vids[0]
    village = await db[c.VILLAGES].find_one({"_id": active_vid})
    village_id = active_vid
    groups = await db[c.GROUPS].find({"village_id": village_id, "is_active": True}).sort("name", 1).to_list()
    group_ids = [group["_id"] for group in groups]
    group_counts = {row["_id"]: row["count"] async for row in await db[c.GIRLS].aggregate([
        {"$match": {"village_id": village_id, "is_deleted": {"$ne": True}, "group_id": {"$in": group_ids}}},
        {"$group": {"_id": "$group_id", "count": {"$sum": 1}}},
    ])} if group_ids else {}
    for group in groups:
        group["girl_count"] = group_counts.get(group["_id"], 0)
    today = today_local()
    month_start, _month_end = period_bounds("monthly", today)
    week_start, _week_end = period_bounds("weekly", today)
    summary = await metrics.activity_summary(db, user["_id"], village_id, month_start, today)
    summary.update(
        girls_total=await db[c.GIRLS].count_documents({"village_id": village_id, "is_deleted": {"$ne": True}}),
        girls_active=await db[c.GIRLS].count_documents({"village_id": village_id, "is_deleted": {"$ne": True}, "enrollment.status": "active"}),
        home_visits_today=await metrics.home_visits(db, user["_id"], village_id, today, today),
        home_visits_this_week=await metrics.home_visits(db, user["_id"], village_id, week_start, today),
        home_visits_this_month=await metrics.home_visits(db, user["_id"], village_id, month_start, today),
        pending_visits=await db[c.HOME_VISITS].count_documents({"village_id": village_id, "volunteer_id": user["_id"], "approval.status": "pending"}),
        pending_reports=await db[c.ACTIVITY_REPORTS].count_documents({"village_id": village_id, "volunteer_id": user["_id"], "approval.status": "pending"}),
    )

    target_docs = await db[c.TARGETS].find({
        "volunteer_id": user["_id"],
        "$or": [{"village_id": village_id}, {"village_id": {"$in": assigned_vids}}, {"village_id": None}],
        "status": "active",
        "period_start": {"$lte": to_dt(today)}, "period_end": {"$gte": to_dt(today)},
    }).sort("period_end", 1).to_list()
    upcoming_target_docs = await db[c.TARGETS].find({
        "volunteer_id": user["_id"],
        "$or": [{"village_id": village_id}, {"village_id": {"$in": assigned_vids}}, {"village_id": None}],
        "status": "active",
        "period_start": {"$gt": to_dt(today)},
    }).sort("period_start", 1).limit(5).to_list()
    thresholds = await get_setting(db, "target_thresholds")
    targets = await with_progress(db, target_docs, thresholds)
    upcoming_targets = await with_progress(db, upcoming_target_docs, thresholds)

    now = utcnow()
    upcoming_events = await db[c.EVENTS].find({
        "village_id": village_id, "status": "scheduled", "start_at": {"$gte": now},
    }).sort("start_at", 1).limit(6).to_list()
    overdue_events = await db[c.EVENTS].find({
        "village_id": village_id, "status": "scheduled", "responsible_volunteer_id": user["_id"],
        "end_at": {"$lt": now},
    }).sort("end_at", -1).limit(6).to_list()
    upcoming_visits = await db[c.HOME_VISITS].find({
        "village_id": village_id, "volunteer_id": user["_id"], "status": "planned",
        "visit_date": {"$gte": to_dt(today)},
    }).sort("visit_date", 1).limit(6).to_list()

    open_case_query = {
        "village_id": village_id, "status": {"$in": OPEN_CASE_STATUSES},
        "$or": [{"sensitive": False}, {"assigned_to": user["_id"]}],
    }
    open_cases = await db[c.CASES].count_documents(open_case_query)
    overdue_case_query = {**open_case_query, "due_date": {"$lt": to_dt(today)}}
    overdue_cases = await db[c.CASES].count_documents(overdue_case_query)
    overdue_case_items = await db[c.CASES].find(overdue_case_query, {"timeline": 0}).sort("due_date", 1).limit(6).to_list()
    upcoming_cases = await db[c.CASES].find({**open_case_query, "due_date": {"$gte": to_dt(today)}}).sort("due_date", 1).limit(6).to_list()
    recent_visits = await db[c.HOME_VISITS].find({
        "village_id": village_id, "volunteer_id": user["_id"],
    }).sort("visit_date", -1).limit(5).to_list()
    recent_reports = await db[c.ACTIVITY_REPORTS].find({
        "village_id": village_id, "volunteer_id": user["_id"],
    }).sort("report_date", -1).limit(5).to_list()

    contacts = await db[c.CONTACTS].find({
        "village_id": village_id, "is_active": True,
    }).to_list()
    by_category = {contact["category"]: contact for contact in contacts}
    mandatory = [
        {"category": category, "present": category in by_category,
         "verified": bool(by_category.get(category, {}).get("verified")),
         "contact_id": str(by_category[category]["_id"]) if category in by_category else None,
         "name": by_category.get(category, {}).get("name")}
        for category in ("hospital_head", "police_patil", "sarpanch", "talathi")
    ]
    unread = await db[c.NOTIFICATIONS].count_documents({"user_id": user["_id"], "is_read": False})

    return {
        "assigned": True, "user": {"id": str(user["_id"]), "name": user.get("name"), "role": user.get("role"),
                                   "village_id": str(village_id), "village_ids": [str(v) for v in assigned_vids]},
        "village": serialize(village), "villages": serialize(all_assigned_villages), "selected_village_id": str(village_id),
        "groups": serialize(groups), "summary": summary,
        "targets": serialize(targets), "upcoming_targets": serialize(upcoming_targets),
        "upcoming_events": serialize(upcoming_events), "overdue_events": serialize(overdue_events),
        "upcoming_visits": serialize(upcoming_visits), "upcoming_cases": serialize(upcoming_cases),
        "overdue_case_items": serialize(overdue_case_items), "open_cases": open_cases, "overdue_cases": overdue_cases,
        "recent_visits": serialize(recent_visits), "recent_reports": serialize(recent_reports),
        "contacts": {"mandatory": mandatory, "complete": all(item["present"] and item["verified"] for item in mandatory)},
        "unread_notifications": unread, "month_start": month_start, "today": today,
    }


@router.get("/me/report")
async def my_report(db: Db, user: CurrentUser, start_date: date | None = None, end_date: date | None = None):
    """Personal activity report, constrained to the signed-in volunteer and current village."""
    if user.get("role") != Role.VOLUNTEER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Volunteer access required")
    today = today_local()
    end = end_date or today
    start = start_date or period_bounds("monthly", today)[0]
    if end > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date cannot be in the future")
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start_date cannot be after end_date")
    if (end - start).days > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Report range is limited to 367 days")
    village_id = user.get("village_id")
    if not village_id:
        return {"assigned": False, "start_date": start, "end_date": end, "summary": {}, "targets": [],
                "visits": [], "activity_reports": [], "events": []}
    await require_permission("reports", "read")(db, user)
    summary = await metrics.activity_summary(db, user["_id"], village_id, start, end)
    s, e = day_range(start, end)
    visits = await db[c.HOME_VISITS].find({"village_id": village_id, "volunteer_id": user["_id"],
                                            "visit_date": {"$gte": s, "$lt": e}}).sort("visit_date", -1).to_list()
    reports = await db[c.ACTIVITY_REPORTS].find({"village_id": village_id, "volunteer_id": user["_id"],
                                                  "report_date": {"$gte": s, "$lt": e}}).sort("report_date", -1).to_list()
    events = await db[c.EVENTS].find({"village_id": village_id, "responsible_volunteer_id": user["_id"],
                                      "start_at": {"$gte": s, "$lt": e}}).sort("start_at", -1).to_list()
    target_docs = await db[c.TARGETS].find({"volunteer_id": user["_id"], "village_id": village_id,
                                             "period_start": {"$lte": to_dt(end)}, "period_end": {"$gte": to_dt(start)}}).to_list()
    targets = await with_progress(db, target_docs)
    return {"assigned": True, "village_id": str(village_id), "start_date": start, "end_date": end,
            "summary": summary, "targets": serialize(targets), "visits": serialize(visits),
            "activity_reports": serialize(reports), "events": serialize(events)}


@router.get("/me/assignment-history")
async def my_assignment_history(db: Db, user: CurrentUser):
    if user.get("role") != Role.VOLUNTEER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Volunteer access required")
    history = await db[c.VOLUNTEER_ASSIGNMENTS].find({"volunteer_id": user["_id"]}).sort(
        [("start_date", -1), ("created_at", -1)]).to_list()
    villages = await _names(db, c.VILLAGES, {item["village_id"] for item in history})
    return [{**serialize(item), "village_name": villages.get(item["village_id"])} for item in history]

@router.get("/me/planned-vs-actual")
async def my_planned_vs_actual(
    db: Db,
    user: CurrentUser,
    period: Literal["daily", "weekly", "monthly"] = "weekly",
):
    """Return planned-versus-actual activity for the signed-in volunteer."""
    if user.get("role") != Role.VOLUNTEER.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Volunteer access required",
        )

    village_id = user.get("village_id")
    if not village_id:
        return {
            "period": period,
            "assigned": False,
            "rows": [],
            "totals": {
                "visits_planned": 0,
                "visits_completed": 0,
                "events_planned": 0,
                "events_conducted": 0,
                "completion_rate": 0,
            },
        }

    await require_permission("dashboard", "read")(db, user)

    today = today_local()

    # Build the reporting buckets.
    if period == "daily":
        first_date = today - timedelta(days=6)
        bucket_starts = [
            first_date + timedelta(days=i)
            for i in range(7)
        ]
    elif period == "weekly":
        current_monday = today - timedelta(days=today.weekday())
        first_date = current_monday - timedelta(weeks=7)
        bucket_starts = [
            first_date + timedelta(weeks=i)
            for i in range(8)
        ]
    else:
        current_month = today.replace(day=1)
        bucket_starts = []

        for offset in range(5, -1, -1):
            month_index = current_month.year * 12 + current_month.month - 1 - offset
            year, month_index = divmod(month_index, 12)
            bucket_starts.append(
                date(year, month_index + 1, 1)
            )

        first_date = bucket_starts[0]

    rows = []
    bucket_by_key = {}

    for bucket_start in bucket_starts:
        if period == "daily":
            key = bucket_start.isoformat()
            label = bucket_start.strftime("%d %b")
        elif period == "weekly":
            key = bucket_start.isoformat()
            label = f"Week of {bucket_start.strftime('%d %b')}"
        else:
            key = bucket_start.strftime("%Y-%m")
            label = bucket_start.strftime("%b %Y")

        row = {
            "period": key,
            "label": label,
            "visits_planned": 0,
            "visits_completed": 0,
            "events_planned": 0,
            "events_conducted": 0,
        }
        rows.append(row)
        bucket_by_key[key] = row

    def bucket_for(day):
        if period == "daily":
            key = day.isoformat()
        elif period == "weekly":
            key = (day - timedelta(days=day.weekday())).isoformat()
        else:
            key = day.strftime("%Y-%m")

        return bucket_by_key.get(key)

    # Calendar dates are stored as UTC-midnight datetimes.
    visit_start = to_dt(first_date)
    visit_end = to_dt(today + timedelta(days=1))

    visits = await db[c.HOME_VISITS].find({
        "volunteer_id": user["_id"],
        "village_id": village_id,
        "visit_date": {
            "$gte": visit_start,
            "$lt": visit_end,
        },
    }).to_list()

    for visit in visits:
        visit_day = to_date(visit.get("visit_date"))
        row = bucket_for(visit_day) if visit_day else None

        if not row:
            continue

        # A visit record represents a scheduled activity; its status
        # tells us whether the activity was completed.
        row["visits_planned"] += 1

        if visit.get("status") == "completed":
            row["visits_completed"] += 1

    # Events are counted only when this volunteer is responsible for them.
    event_start, event_end = local_day_bounds(first_date, today)

    events = await db[c.EVENTS].find({
        "responsible_volunteer_id": user["_id"],
        "village_id": village_id,
        "start_at": {
            "$gte": event_start,
            "$lt": event_end,
        },
    }).to_list()

    for event in events:
        start_at = event.get("start_at")
        if not start_at:
            continue

        event_day = start_at.astimezone(local_tz()).date()
        row = bucket_for(event_day)

        if not row:
            continue

        if event.get("planned", False):
            row["events_planned"] += 1

        if event.get("status") == "completed":
            row["events_conducted"] += 1

    totals = {
        "visits_planned": sum(r["visits_planned"] for r in rows),
        "visits_completed": sum(r["visits_completed"] for r in rows),
        "events_planned": sum(r["events_planned"] for r in rows),
        "events_conducted": sum(r["events_conducted"] for r in rows),
    }

    planned = totals["visits_planned"] + totals["events_planned"]
    completed = totals["visits_completed"] + totals["events_conducted"]

    totals["completion_rate"] = (
        round(completed / planned * 100)
        if planned else 0
    )

    return {
        "period": period,
        "assigned": True,
        "rows": rows,
        "totals": totals,
    }


@router.get("/{volunteer_id}")
async def get_volunteer(volunteer_id: str, db: Db, _: Stakeholder):
    """Volunteer (Tai) master: profile, assigned villages and Kishori Groups."""
    v = await _volunteer(db, volunteer_id)
    out = serialize(v)
    from app.core.deps import user_village_ids
    v_ids = user_village_ids(v)
    if v_ids:
        villages = await db[c.VILLAGES].find({"_id": {"$in": v_ids}}).to_list()
        out["villages"] = serialize(villages)
        out["village"] = serialize(villages[0])
        groups = await db[c.GROUPS].find({"village_id": {"$in": v_ids}, "is_active": True}).sort("name", 1).to_list()
        out["village_groups"] = [{**serialize(g), "assigned_to_this_volunteer": g["_id"] in v.get("group_ids", [])}
                                 for g in groups]
    out["current_assignment"] = serialize(await assignments.current_assignment(db, v["_id"]))
    out["current_assignments"] = serialize(await assignments.current_assignments(db, v["_id"]))
    return out


@router.get("/{volunteer_id}/assignments")
async def assignment_history(volunteer_id: str, db: Db, _: Stakeholder):
    v = await _volunteer(db, volunteer_id)
    history = await db[c.VOLUNTEER_ASSIGNMENTS].find({"volunteer_id": v["_id"]}).sort([("start_date", -1), ("created_at", -1)]).to_list()
    villages = await _names(db, c.VILLAGES, {h["village_id"] for h in history})
    actors = await _names(db, c.USERS, {h.get("assigned_by") for h in history})
    return [{**serialize(h), "village_name": villages.get(h["village_id"]),
             "assigned_by_name": actors.get(h.get("assigned_by"))} for h in history]


@router.post("/{volunteer_id}/assign")
async def assign(volunteer_id: str, body: AssignRequest, db: Db, actor: Stakeholder):
    """Give an unassigned volunteer their (single) village. Use /reassign to move an assigned volunteer."""
    v = await _volunteer(db, volunteer_id)
    if not v["is_active"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot assign an inactive volunteer")
    # Volunteers (Tais) can be assigned to multiple villages concurrently
    village = await assignments.load_active_village(db, body.village_id)
    assignment = await assignments.assign_village(
        db, v, body.village_id, body.group_ids, actor, "Initial assignment", body.effective_date)
    await notifications.notify(db, v["_id"], "assigned", f"You have been assigned to {village['name']}",
                               entity_type="village", entity_id=village["_id"])
    await audit.log(db, actor, "reassign", "user", v["_id"], f"Assigned {v['name']} to {village['name']}",
                    {"village_id": {"from": None, "to": village["_id"]}})
    return {"volunteer": serialize(await db[c.USERS].find_one({"_id": v["_id"]})), "assignment": serialize(assignment)}


@router.post("/{volunteer_id}/reassign")
async def reassign(volunteer_id: str, body: ReassignRequest, db: Db, actor: Stakeholder):
    """Move a volunteer to another village (closing the current assignment), set their groups,
    and decide what happens to their open targets."""
    v = await _volunteer(db, volunteer_id)
    if not v["is_active"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot reassign an inactive volunteer")
    old_village = v.get("village_id")
    new_village = await assignments.load_active_village(db, body.village_id)
    await assignments.validate_groups(db, new_village["_id"], body.group_ids)

    curr = await assignments.current_assignment(db, v["_id"], new_village["_id"])
    if curr and old_village == new_village["_id"] and set(curr.get("group_ids", [])) == set(oids(body.group_ids)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Volunteer is already assigned to this village and groups")

    target_result = {"action": body.targets.action, "affected": 0}
    if old_village and old_village != new_village["_id"]:
        target_result = await handle_reassignment(
            db, v, new_village["_id"], body.targets.action,
            oid(body.targets.transfer_to_volunteer_id) if body.targets.transfer_to_volunteer_id else None,
            actor, body.reason,
        )
        await assignments.unassign_village(db, v, old_village, actor, body.reason)
        v = await db[c.USERS].find_one({"_id": v["_id"]})
    assignment = await assignments.assign_village(
        db, v, body.village_id, body.group_ids, actor, body.reason, body.effective_date)
    await notifications.notify(db, v["_id"], "reassigned", f"You have been assigned to {new_village['name']}",
                               body.reason, entity_type="village", entity_id=new_village["_id"])
    await audit.log(db, actor, "reassign", "user", v["_id"], f"Reassigned {v['name']} to {new_village['name']}",
                    {"village_id": {"from": old_village, "to": new_village["_id"]},
                     "group_ids": {"from": v.get("group_ids", []), "to": assignment["group_ids"]}},
                    {"reason": body.reason, "targets": target_result})
    return {"volunteer": serialize(await db[c.USERS].find_one({"_id": v["_id"]})),
            "assignment": serialize(assignment), "targets": target_result}


@router.put("/{volunteer_id}/groups")
async def set_groups(volunteer_id: str, body: GroupAssignment, db: Db, actor: Stakeholder):
    v = await _volunteer(db, volunteer_id)
    groups = await assignments.set_groups(db, v, body.group_ids)
    await audit.log(db, actor, "update", "user", v["_id"], f"Updated groups for {v['name']}",
                    {"group_ids": {"from": v.get("group_ids", []), "to": groups}})
    return serialize(await db[c.USERS].find_one({"_id": v["_id"]}))


@router.get("/{volunteer_id}/dashboard")
async def volunteer_dashboard(volunteer_id: str, db: Db, _: Stakeholder):
    """Targets, completed visits, events, pending forms, open cases and overdue actions."""
    v = await _volunteer(db, volunteer_id)
    vid, village = v["_id"], v.get("village_id")
    today = today_local()
    week_start, _w = period_bounds("weekly", today)
    month_start, _m = period_bounds("monthly", today)
    now = utcnow()
    targets = await db[c.TARGETS].find({"volunteer_id": vid, "status": "active",
                                        "period_start": {"$lte": to_dt(today)}, "period_end": {"$gte": to_dt(today)}}).to_list()
    upcoming_targets = await db[c.TARGETS].find({"volunteer_id": vid, "status": "active",
                                                 "period_start": {"$gt": to_dt(today)}}).sort("period_start", 1).limit(5).to_list()
    month_s, month_e = local_day_bounds(month_start, today)
    rules = await get_setting(db, "reporting")
    last7 = activity.working_days(today - timedelta(days=7), today - timedelta(days=rules["grace_days"]), rules["working_days"])
    s7, e7 = day_range(today - timedelta(days=7), today)
    submitted = {r["report_date"].date() async for r in db[c.ACTIVITY_REPORTS].find(
        {"volunteer_id": vid, "report_date": {"$gte": s7, "$lt": e7}}, {"report_date": 1})}
    overdue_cases = await db[c.CASES].find({"assigned_to": vid, "status": {"$in": OPEN_CASE_STATUSES},
                                            "due_date": {"$lt": to_dt(today)}}, {"timeline": 0}).to_list()
    overdue_events = await db[c.EVENTS].find({"responsible_volunteer_id": vid, "status": "scheduled",
                                              "end_at": {"$lt": now}}, {"attendance": 0}).to_list()
    missed_visits = await db[c.HOME_VISITS].find({"volunteer_id": vid, "status": "planned",
                                                  "visit_date": {"$lt": to_dt(today)}}).to_list()
    return {
        "volunteer": {"id": str(vid), "name": v["name"], "village_id": str(village) if village else None},
        "targets": serialize(await with_progress(db, targets)),
        "upcoming_targets": serialize(upcoming_targets),
        "home_visits": {
            "today": await metrics.home_visits(db, vid, village, today, today),
            "this_week": await metrics.home_visits(db, vid, village, week_start, today),
            "this_month": await metrics.home_visits(db, vid, village, month_start, today),
        },
        "events": {
            "completed_this_month": await db[c.EVENTS].count_documents(
                {"responsible_volunteer_id": vid, "status": "completed", "start_at": {"$gte": month_s, "$lt": month_e}}),
            "upcoming": serialize(await db[c.EVENTS].find(
                {"responsible_volunteer_id": vid, "status": "scheduled", "end_at": {"$gte": now}},
                {"attendance": 0}).sort("start_at", 1).limit(10).to_list()),
        },
        "pending_forms": {
            "missing_daily_reports": [d for d in last7 if d not in submitted],
            "event_reports_due": len(overdue_events),
            "planned_visits_not_completed": len(missed_visits),
        },
        "open_cases": await db[c.CASES].count_documents({"assigned_to": vid, "status": {"$in": OPEN_CASE_STATUSES}}),
        "village_open_cases": await db[c.CASES].count_documents({"village_id": village, "status": {"$in": OPEN_CASE_STATUSES}}) if village else 0,
        "overdue_actions": {
            "cases": serialize(overdue_cases),
            "events_without_report": serialize(overdue_events),
            "missed_planned_visits": serialize(missed_visits),
        },
        "upcoming_visits": serialize(await db[c.HOME_VISITS].find(
            {"volunteer_id": vid, "status": "planned", "visit_date": {"$gte": to_dt(today)}}).sort("visit_date", 1).limit(10).to_list()),
    }


@router.get("/{volunteer_id}/activity")
async def activity_view(
    volunteer_id: str,
    db: Db,
    _: Stakeholder,
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Daily / weekly / monthly activity counts."""
    v = await _volunteer(db, volunteer_id)
    end = end_date or today_local()
    default_span = {"daily": 30, "weekly": 7 * 12, "monthly": 365}[granularity]
    start = start_date or end - timedelta(days=default_span - 1)
    if (end - start).days > 731:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Range is limited to two years")
    series = await activity.timeseries(db, start, end, granularity, volunteer_id=v["_id"])
    return {"volunteer_id": volunteer_id, "granularity": granularity, "start": start, "end": end, "series": series}


@router.get("/{volunteer_id}/history")
async def activity_history(volunteer_id: str, db: Db, _: Stakeholder, limit: int = Query(50, le=200)):
    """Chronological feed of the volunteer's submissions and records."""
    v = await _volunteer(db, volunteer_id)
    vid = v["_id"]
    items = []
    async for r in db[c.ACTIVITY_REPORTS].find({"volunteer_id": vid}).sort("report_date", -1).limit(limit):
        items.append({"type": "activity_report", "date": r["report_date"], "id": r["_id"], "village_id": r["village_id"],
                      "summary": f"{len(r.get('activities', []))} activities, {r.get('home_visits_count', 0)} home visits"})
    async for h in db[c.HOME_VISITS].find({"volunteer_id": vid}).sort("visit_date", -1).limit(limit):
        items.append({"type": "home_visit", "date": h["visit_date"], "id": h["_id"], "village_id": h["village_id"],
                      "summary": f"{h['status']} {h['purpose']} visit ({len(h.get('girl_ids', []))} girls)"})
    async for e in db[c.EVENTS].find({"responsible_volunteer_id": vid}, {"attendance": 0}).sort("start_at", -1).limit(limit):
        items.append({"type": "event", "date": e["start_at"], "id": e["_id"], "village_id": e["village_id"],
                      "summary": f"{e['title']} ({e['status']})"})
    pipeline = [{"$match": {"timeline.by": vid}}, {"$unwind": "$timeline"}, {"$match": {"timeline.by": vid}},
                {"$sort": {"timeline.at": -1}}, {"$limit": limit}]
    async for cs in await db[c.CASES].aggregate(pipeline):
        items.append({"type": f"case_{cs['timeline']['type']}", "date": cs["timeline"]["at"], "id": cs["_id"],
                      "village_id": cs["village_id"], "summary": f"{cs['case_code']}: {cs['timeline']['text'][:120]}"})
    items.sort(key=lambda x: x["date"], reverse=True)
    return serialize(items[:limit])


@router.get("/{volunteer_id}/coverage")
async def field_coverage(volunteer_id: str, db: Db, _: Stakeholder,
                         start_date: date | None = None, end_date: date | None = None):
    """How much of the assigned village the volunteer reached: girls, groups and visit locations."""
    v = await _volunteer(db, volunteer_id)
    village = v.get("village_id")
    if not village:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Volunteer has no assigned village")
    end = end_date or today_local()
    start = start_date or period_bounds("monthly", end)[0]
    reached = await metrics.girls_covered_ids(db, v["_id"], village, start, end)
    total_girls = await db[c.GIRLS].count_documents({"village_id": village, "is_deleted": {"$ne": True}})
    groups = await db[c.GROUPS].find({"village_id": village, "is_active": True}, {"name": 1, "group_type": 1}).to_list()
    s, e = day_range(start, end)
    ls, le = local_day_bounds(start, end)
    met = set()
    async for r in db[c.ACTIVITY_REPORTS].find({"volunteer_id": v["_id"], "report_date": {"$gte": s, "$lt": e}}, {"group_ids": 1}):
        met.update(r.get("group_ids") or [])
    async for ev in db[c.EVENTS].find({"responsible_volunteer_id": v["_id"], "status": "completed",
                                       "start_at": {"$gte": ls, "$lt": le}}, {"group_ids": 1}):
        met.update(ev.get("group_ids") or [])
    points = [{"lat": h["gps"]["lat"], "lng": h["gps"]["lng"], "date": h["visit_date"], "id": h["_id"]}
              async for h in db[c.HOME_VISITS].find({"volunteer_id": v["_id"], "visit_date": {"$gte": s, "$lt": e},
                                                     "gps": {"$ne": None}}, {"gps": 1, "visit_date": 1})]
    return {
        "start": start, "end": end,
        "girls": {"total": total_girls, "reached": len(reached),
                  "coverage_pct": round(100 * len(reached) / total_girls, 1) if total_girls else None},
        "groups": {"total": len(groups), "met": sum(1 for g in groups if g["_id"] in met),
                   "not_met": serialize([g for g in groups if g["_id"] not in met])},
        "visit_locations": serialize(points),
    }


@router.post("/{volunteer_id}/unassign/{village_id}")
async def unassign_volunteer_village(volunteer_id: str, village_id: str, db: Db, actor: Stakeholder, reason: str = "Unassignment"):
    """Remove one assigned village from a Tai."""
    v = await _volunteer(db, volunteer_id)
    await assignments.unassign_village(db, v, village_id, actor, reason)
    await audit.log(db, actor, "unassign", "user", v["_id"], f"Unassigned {v['name']} from village {village_id}")
    return serialize(await db[c.USERS].find_one({"_id": v["_id"]}))


@router.post("/handover")
async def handover_village(body: HandoverRequest, db: Db, actor: Stakeholder):
    """Hand over a village from one Tai to another Tai."""
    from_vol = await _volunteer(db, body.from_volunteer_id)
    to_vol = await _volunteer(db, body.to_volunteer_id)

    res = await assignments.handover_village(
        db,
        from_vol,
        to_vol,
        body.village_id,
        actor,
        body.reason,
        transfer_groups=body.transfer_groups,
        transfer_cases=body.transfer_cases,
        transfer_targets=body.transfer_targets,
        effective_date=body.effective_date,
    )

    village = res["village"]
    await notifications.notify(
        db,
        from_vol["_id"],
        "village_handover",
        f"Village {village['name']} has been handed over to {to_vol['name']}",
        body.reason,
        entity_type="village",
        entity_id=village["_id"],
    )
    await notifications.notify(
        db,
        to_vol["_id"],
        "village_handover",
        f"Village {village['name']} has been handed over to you from {from_vol['name']}",
        body.reason,
        entity_type="village",
        entity_id=village["_id"],
    )
    await audit.log(
        db,
        actor,
        "handover",
        "village",
        village["_id"],
        f"Handed over {village['name']} from {from_vol['name']} to {to_vol['name']}",
        {
            "from_volunteer_id": from_vol["_id"],
            "to_volunteer_id": to_vol["_id"],
            "groups_transferred": len(res["group_ids"]),
            "cases_transferred": res["cases_transferred"],
            "targets_transferred": res["targets_transferred"],
            "reason": body.reason,
        },
    )

    return {
        "success": True,
        "message": f"Village {village['name']} handed over from {from_vol['name']} to {to_vol['name']}.",
        "from_volunteer": serialize(await db[c.USERS].find_one({"_id": from_vol["_id"]})),
        "to_volunteer": serialize(await db[c.USERS].find_one({"_id": to_vol["_id"]})),
        "assignment": serialize(res["assignment"]),
        "groups_transferred": len(res["group_ids"]),
        "cases_transferred": res["cases_transferred"],
        "targets_transferred": res["targets_transferred"],
    }


@router.post("/{volunteer_id}/handover")
async def handover_volunteer_village(volunteer_id: str, body: HandoverRequest, db: Db, actor: Stakeholder):
    """Convenience alias for handover initiated from a specific volunteer's detail screen."""
    if str(body.from_volunteer_id) != volunteer_id:
        body.from_volunteer_id = volunteer_id
    return await handover_village(body, db, actor)

