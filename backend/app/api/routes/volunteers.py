"""Volunteer management (PRD 4.7) and reassignment (PRD 4.1)."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import Db, Stakeholder
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.users import AssignRequest, GroupAssignment, ReassignRequest
from app.services import activity, assignments, audit, metrics, notifications
from app.services.app_settings import get_setting
from app.services.beneficiaries import OPEN_CASE_STATUSES
from app.services.events import local_day_bounds
from app.services.targets import handle_reassignment, with_progress
from app.utils.dates import day_range, period_bounds, to_date, to_dt, today_local, utcnow
from app.utils.mongo import ObjectIdStr, get_or_404, oid, serialize

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
    if assigned is not None:
        query["village_id"] = {"$ne": None} if assigned else None
    if village_id:
        query["village_id"] = oid(village_id)
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if is_active is not None:
        query["is_active"] = is_active
    vols = await db[c.USERS].find(query).sort("name", 1).to_list()
    villages = await _names(db, c.VILLAGES, {v.get("village_id") for v in vols})
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
            "village_name": villages.get(v.get("village_id")),
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
    villages = await _names(db, c.VILLAGES, {v.get("village_id") for v in vols})
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
            "village_name": villages.get(v.get("village_id")),
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
    villages = await _names(db, c.VILLAGES, {v.get("village_id") for v in vols})
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
            "village_name": villages.get(v.get("village_id")),
            "expected": len(due), "submitted": len([d for d in due if d in submitted]),
            "missing_dates": missing, "missing_count": len(missing),
            "submission_rate": round(1 - len(missing) / len(due), 2) if due else None,
            "pending_event_reports": pending_event_reports,
        })
    rows.sort(key=lambda r: -r["missing_count"])
    return {"start": start, "end": end, "expected_days": len(expected_days),
            "defaulters": sum(1 for r in rows if r["missing_count"] or r["pending_event_reports"]), "volunteers": rows}


@router.get("/{volunteer_id}")
async def get_volunteer(volunteer_id: str, db: Db, _: Stakeholder):
    """Volunteer master: profile, the single assigned village and its Kishori Groups."""
    v = await _volunteer(db, volunteer_id)
    out = serialize(v)
    if v.get("village_id"):
        out["village"] = serialize(await db[c.VILLAGES].find_one({"_id": v["village_id"]}))
        groups = await db[c.GROUPS].find({"village_id": v["village_id"], "is_active": True}).sort("name", 1).to_list()
        out["village_groups"] = [{**serialize(g), "assigned_to_this_volunteer": g["_id"] in v.get("group_ids", [])}
                                 for g in groups]
    out["current_assignment"] = serialize(await assignments.current_assignment(db, v["_id"]))
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
    if v.get("village_id"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Volunteer already has a village; use reassign to move them")
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

    target_result = {"action": body.targets.action, "affected": 0}
    if old_village and old_village != new_village["_id"]:
        target_result = await handle_reassignment(
            db, v, new_village["_id"], body.targets.action,
            oid(body.targets.transfer_to_volunteer_id) if body.targets.transfer_to_volunteer_id else None,
            actor, body.reason,
        )
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
