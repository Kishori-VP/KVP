"""Stakeholder dashboard (PRD 4.10)."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import Db, Stakeholder
from app.core.permissions import Role
from app.db import collections as c
from app.services import activity, metrics
from app.services.alerts import compute_alerts
from app.services.beneficiaries import OPEN_CASE_STATUSES, birth_year_range_for_band
from app.services.events import local_day_bounds
from app.services.targets import with_progress
from app.utils.dates import PeriodType, period_bounds, to_dt, today_local, utcnow
from app.utils.mongo import ObjectIdStr, oid, serialize

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _village_scope(db, taluka_id: str | None, village_id: str | None) -> list | None:
    """Resolve an optional taluka/village filter to a list of village ids (None = everything)."""
    if village_id:
        return [oid(village_id)]
    if taluka_id:
        return [v["_id"] async for v in db[c.VILLAGES].find({"taluka_id": oid(taluka_id)}, {"_id": 1})]
    return None


def _vmatch(village_ids: list | None, field: str = "village_id") -> dict:
    return {field: {"$in": village_ids}} if village_ids is not None else {}


async def _count_by(db, coll: str, match: dict, key: str) -> dict:
    pipeline = [{"$match": match}, {"$group": {"_id": f"${key}", "n": {"$sum": 1}}}]
    return {str(r["_id"]) if r["_id"] is not None else "unknown": r["n"] async for r in await db[coll].aggregate(pipeline)}


@router.get("/summary")
async def summary(
    db: Db,
    _: Stakeholder,
    period: PeriodType = "monthly",
    reference_date: date | None = None,
    taluka_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
):
    """Headline KPI tiles."""
    if period == "custom":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Use a named period")
    vids = await _village_scope(db, taluka_id, village_id)
    start, end = period_bounds(period, reference_date)
    upto = min(end, today_local())
    girl_match = {"is_deleted": {"$ne": True}, **_vmatch(vids)}
    village_q = {"status": "active", **({"_id": {"$in": vids}} if vids is not None else {})}
    talukas = await db[c.VILLAGES].distinct("taluka_id", village_q)
    ls, le = local_day_bounds(start, end)
    now = utcnow()
    act = await metrics.activity_summary(db, None, None, start, upto) if vids is None else None
    if act is None:
        # Sum per village when a scope is applied.
        act = {}
        for vid in vids:
            part = await metrics.activity_summary(db, None, vid, start, upto)
            for k, v in part.items():
                act[k] = act.get(k, 0) + v
    return {
        "period": period, "start": start, "end": end,
        "girls_enrolled": await db[c.GIRLS].count_documents({**girl_match, "enrollment.status": "active"}),
        "girls_total": await db[c.GIRLS].count_documents(girl_match),
        "villages": await db[c.VILLAGES].count_documents(village_q),
        "talukas": len(talukas),
        "districts": len(await db[c.TALUKAS].distinct("district", {"_id": {"$in": talukas}})),
        "kishori_groups": await db[c.GROUPS].count_documents({"group_type": "kishori", "is_active": True, **_vmatch(vids)}),
        "bal_panchayat_groups": await db[c.GROUPS].count_documents({"group_type": "bal_panchayat", "is_active": True, **_vmatch(vids)}),
        "active_volunteers": await db[c.USERS].count_documents({"role": Role.VOLUNTEER.value, "is_active": True, **_vmatch(vids, "village_ids")}),
        "unassigned_volunteers": await db[c.USERS].count_documents(
            {"role": Role.VOLUNTEER.value, "is_active": True, "village_id": None}) if vids is None else 0,
        "events_conducted": await db[c.EVENTS].count_documents({"status": "completed", "start_at": {"$gte": ls, "$lt": le}, **_vmatch(vids)}),
        "events_upcoming": await db[c.EVENTS].count_documents({"status": "scheduled", "end_at": {"$gte": now}, **_vmatch(vids)}),
        "events_overdue": await db[c.EVENTS].count_documents({"status": "scheduled", "end_at": {"$lt": now}, **_vmatch(vids)}),
        "home_visits": act["home_visits"],
        "group_meetings": act["group_meetings"],
        "girls_reached": act["girls_covered"],
        "event_attendance": act["event_attendance"],
        "open_cases": await db[c.CASES].count_documents({"status": {"$in": OPEN_CASE_STATUSES}, **_vmatch(vids)}),
        "critical_open_cases": await db[c.CASES].count_documents(
            {"status": {"$in": OPEN_CASE_STATUSES}, "severity": "critical", **_vmatch(vids)}),
    }


@router.get("/trends")
async def trends(
    db: Db,
    _: Stakeholder,
    granularity: Literal["daily", "weekly", "monthly"] = "monthly",
    start_date: date | None = None,
    end_date: date | None = None,
    taluka_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
):
    """Home visits, meetings, events and attendance over time."""
    end = end_date or today_local()
    default_days = {"daily": 30, "weekly": 84, "monthly": 365}[granularity]
    start = start_date or end - timedelta(days=default_days - 1)
    if (end - start).days > 1100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Range is limited to three years")
    vids = await _village_scope(db, taluka_id, village_id)
    series = await activity.timeseries(db, start, end, granularity, village_ids=vids)
    return {"granularity": granularity, "start": start, "end": end, "series": series}


@router.get("/cases")
async def cases_breakdown(db: Db, _: Stakeholder, taluka_id: ObjectIdStr | None = None, village_id: ObjectIdStr | None = None):
    """Open cases by severity and category, plus ageing."""
    vids = await _village_scope(db, taluka_id, village_id)
    match = {"status": {"$in": OPEN_CASE_STATUSES}, **_vmatch(vids)}
    pipeline = [{"$match": match}, {"$group": {"_id": {"category": "$category", "severity": "$severity"}, "n": {"$sum": 1}}}]
    matrix: dict = {}
    async for r in await db[c.CASES].aggregate(pipeline):
        matrix.setdefault(r["_id"]["category"], {})[r["_id"]["severity"]] = r["n"]
    today = to_dt(today_local())
    return {
        "by_severity": await _count_by(db, c.CASES, match, "severity"),
        "by_category": await _count_by(db, c.CASES, match, "category"),
        "by_status": await _count_by(db, c.CASES, match, "status"),
        "category_x_severity": matrix,
        "overdue": await db[c.CASES].count_documents({**match, "due_date": {"$lt": today}}),
        "opened_last_30_days": await db[c.CASES].count_documents(
            {**_vmatch(vids), "opened_at": {"$gte": utcnow() - timedelta(days=30)}}),
        "resolved_last_30_days": await db[c.CASES].count_documents(
            {**_vmatch(vids), "resolved_at": {"$gte": utcnow() - timedelta(days=30)}}),
    }


@router.get("/villages")
async def village_status(db: Db, _: Stakeholder, taluka_id: ObjectIdStr | None = None):
    """Village-wise activity status and map data (On Track / Delayed / No Recent Activity)."""
    q: dict = {"status": "active"}
    if taluka_id:
        q["taluka_id"] = oid(taluka_id)
    villages = await db[c.VILLAGES].find(q).sort("name", 1).to_list()
    statuses = await activity.village_activity_status(db)
    ids = [v["_id"] for v in villages]
    girls = await _count_by(db, c.GIRLS, {"village_id": {"$in": ids}, "is_deleted": {"$ne": True}}, "village_id")
    open_cases = await _count_by(db, c.CASES, {"village_id": {"$in": ids}, "status": {"$in": OPEN_CASE_STATUSES}}, "village_id")
    # A volunteer can work in several villages: count her in each of them.
    vols: dict = {}
    async for row in await db[c.USERS].aggregate([
        {"$match": {"village_ids": {"$in": ids}, "role": "volunteer", "is_active": True}},
        {"$unwind": "$village_ids"}, {"$match": {"village_ids": {"$in": ids}}},
        {"$group": {"_id": "$village_ids", "n": {"$sum": 1}}},
    ]):
        vols[row["_id"]] = row["n"]
    month_start, _e = period_bounds("monthly")
    rows = []
    for v in villages:
        st = statuses.get(v["_id"], {"status": "no_recent_activity", "last_activity": None, "days_since": None})
        rows.append({
            "village_id": str(v["_id"]), "name": v["name"], "name_mr": v.get("name_mr"),
            "location": v.get("location"), **serialize(st),
            "girls": girls.get(str(v["_id"]), 0), "open_cases": open_cases.get(str(v["_id"]), 0),
            "volunteers": vols.get(str(v["_id"]), 0),
            "home_visits_this_month": await metrics.home_visits(db, None, v["_id"], month_start, today_local()),
        })
    counts: dict = {"on_track": 0, "delayed": 0, "no_recent_activity": 0}
    for r in rows:
        counts[r["status"]] += 1
    return {"counts": counts, "villages": rows,
            "unmapped": [r["name"] for r in rows if not r["location"]]}


@router.get("/targets")
async def target_achievement(db: Db, _: Stakeholder, on_date: date | None = None, taluka_id: ObjectIdStr | None = None):
    """Volunteer-wise achievement of currently running targets."""
    d = to_dt(on_date or today_local())
    q: dict = {"status": "active", "period_start": {"$lte": d}, "period_end": {"$gte": d}}
    if taluka_id:
        q["taluka_id"] = oid(taluka_id)
    enriched = await with_progress(db, await db[c.TARGETS].find(q).to_list())
    names = {u["_id"]: u["name"] for u in await db[c.USERS].find({"role": "volunteer"}, {"name": 1}).to_list()}
    per_vol: dict = {}
    for t in enriched:
        row = per_vol.setdefault(t["volunteer_id"], {"volunteer_id": str(t["volunteer_id"]),
                                                     "name": names.get(t["volunteer_id"]), "targets": []})
        row["targets"].append({"id": str(t["_id"]), "title": t["title"], "target_value": t["target_value"], **t["progress"]})
    rows = []
    for row in per_vol.values():
        pcts = [min(t["progress_pct"], 100) for t in row["targets"]]
        row["avg_achievement_pct"] = round(sum(pcts) / len(pcts), 1)
        row["at_risk_or_missed"] = sum(1 for t in row["targets"] if t["status"] in ("at_risk", "missed"))
        rows.append(row)
    rows.sort(key=lambda r: -r["avg_achievement_pct"])
    by_status: dict = {}
    for t in enriched:
        by_status[t["progress"]["status"]] = by_status.get(t["progress"]["status"], 0) + 1
    return {"volunteers": rows, "by_status": by_status, "total_targets": len(enriched)}


@router.get("/participation")
async def participation(db: Db, _: Stakeholder, months: int = Query(6, ge=1, le=24),
                        taluka_id: ObjectIdStr | None = None, village_id: ObjectIdStr | None = None):
    """Meeting/event attendance and participation trends."""
    vids = await _village_scope(db, taluka_id, village_id)
    end = today_local()
    start = (end.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    series = await activity.timeseries(db, start, end, "monthly", village_ids=vids)
    cutoff = to_dt(end - timedelta(days=90))
    girl_match = {"is_deleted": {"$ne": True}, **_vmatch(vids)}
    total = await db[c.GIRLS].count_documents(girl_match)
    active = await db[c.GIRLS].count_documents({**girl_match, "last_participation_at": {"$gte": cutoff}})
    return {
        "series": [{"period": s["period"], "event_attendance": s["attendance"], "events_completed": s["events_completed"],
                    "group_meetings": s["group_meetings"], "meeting_participation": s["meeting_participation"],
                    "home_visits": s["home_visits"]} for s in series],
        "girls_active_last_90_days": active,
        "girls_total": total,
        "active_participation_pct": round(100 * active / total, 1) if total else None,
    }


@router.get("/health")
async def health_indicators(db: Db, _: Stakeholder, taluka_id: ObjectIdStr | None = None, village_id: ObjectIdStr | None = None):
    """Anaemia coverage and other impact indicators."""
    vids = await _village_scope(db, taluka_id, village_id)
    girl_match = {"is_deleted": {"$ne": True}, **_vmatch(vids)}
    total = await db[c.GIRLS].count_documents(girl_match)
    screened = await db[c.GIRLS].count_documents({**girl_match, "health_summary.latest_hb": {"$ne": None}})
    anaemia = await _count_by(db, c.GIRLS, {**girl_match, "health_summary.latest_hb": {"$ne": None}},
                              "health_summary.anaemia_status")
    anaemic = sum(v for k, v in anaemia.items() if k in ("mild", "moderate", "severe"))
    lo, hi = birth_year_range_for_band("15_19")
    lo2, hi2 = birth_year_range_for_band("10_14")
    open_match = {"status": {"$in": OPEN_CASE_STATUSES}, **_vmatch(vids)}
    return {
        "girls_total": total,
        "hb_screened": screened,
        "hb_screening_coverage_pct": round(100 * screened / total, 1) if total else None,
        "anaemia_distribution": anaemia,
        "anaemia_prevalence_pct": round(100 * anaemic / screened, 1) if screened else None,
        "school_status": await _count_by(db, c.GIRLS, girl_match, "school_status"),
        "age_bands": {
            "10_14": await db[c.GIRLS].count_documents({**girl_match, "birth_year": {"$gte": lo2, "$lte": hi2}}),
            "15_19": await db[c.GIRLS].count_documents({**girl_match, "birth_year": {"$gte": lo, "$lte": hi}}),
            "unknown": await db[c.GIRLS].count_documents({**girl_match, "birth_year": None}),
        },
        "open_concerns_by_category": await _count_by(db, c.CASES, open_match, "category"),
    }


@router.get("/alerts")
async def alerts(db: Db, _: Stakeholder, taluka_id: ObjectIdStr | None = None, village_id: ObjectIdStr | None = None):
    """Overdue reports, unresolved cases, inactive villages, missed targets."""
    return await compute_alerts(db, await _village_scope(db, taluka_id, village_id))


@router.get("/drilldown")
async def drilldown(
    db: Db,
    _: Stakeholder,
    level: Literal["district", "taluka", "village", "group", "volunteer", "girl"] = "district",
    parent_id: str | None = Query(None, description="District name, or the id of the parent taluka/village/group"),
    period: PeriodType = "monthly",
):
    """district/taluka -> village -> group / volunteer -> girl, with metrics at each level."""
    start, end = period_bounds(period if period != "custom" else "monthly")
    upto = min(end, today_local())
    statuses = await activity.village_activity_status(db)

    async def village_metrics(vids: list) -> dict:
        girls = await db[c.GIRLS].count_documents({"village_id": {"$in": vids}, "is_deleted": {"$ne": True}})
        cases = await db[c.CASES].count_documents({"village_id": {"$in": vids}, "status": {"$in": OPEN_CASE_STATUSES}})
        visits = 0
        for vid in vids:
            visits += await metrics.home_visits(db, None, vid, start, upto)
        return {"girls": girls, "open_cases": cases, "home_visits": visits}

    rows = []
    if level == "district":
        for d in await db[c.TALUKAS].distinct("district"):
            tids = [t["_id"] async for t in db[c.TALUKAS].find({"district": d}, {"_id": 1})]
            vids = [v["_id"] async for v in db[c.VILLAGES].find({"taluka_id": {"$in": tids}}, {"_id": 1})]
            rows.append({"id": d, "name": d, "talukas": len(tids), "villages": len(vids), **await village_metrics(vids),
                         "next_level": "taluka"})
    elif level == "taluka":
        q = {"district": parent_id} if parent_id else {}
        async for t in db[c.TALUKAS].find(q).sort("name", 1):
            vids = [v["_id"] async for v in db[c.VILLAGES].find({"taluka_id": t["_id"]}, {"_id": 1})]
            rows.append({"id": str(t["_id"]), "name": t["name"], "name_mr": t.get("name_mr"), "villages": len(vids),
                         **await village_metrics(vids), "next_level": "village"})
    elif level == "village":
        q = {"taluka_id": oid(parent_id)} if parent_id else {}
        async for v in db[c.VILLAGES].find(q).sort("name", 1):
            rows.append({"id": str(v["_id"]), "name": v["name"], "name_mr": v.get("name_mr"),
                         "groups": await db[c.GROUPS].count_documents({"village_id": v["_id"], "group_type": "kishori"}),
                         "volunteers": await db[c.USERS].count_documents({"village_ids": v["_id"], "role": "volunteer", "is_active": True}),
                         "activity_status": statuses.get(v["_id"], {}).get("status"),
                         **await village_metrics([v["_id"]]), "next_level": "group|volunteer"})
    elif level == "group":
        if not parent_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "parent_id (village id) is required")
        async for g in db[c.GROUPS].find({"village_id": oid(parent_id)}).sort([("group_type", 1), ("name", 1)]):
            girls = await db[c.GIRLS].count_documents({"group_id": g["_id"], "is_deleted": {"$ne": True}})
            rows.append({"id": str(g["_id"]), "name": g["name"], "name_en": g.get("name_en"), "group_type": g["group_type"], "girls": girls,
                         "responsible_volunteer_id": str(g["responsible_volunteer_id"]) if g.get("responsible_volunteer_id") else None,
                         "open_cases": await db[c.CASES].count_documents({"status": {"$in": OPEN_CASE_STATUSES},
                            "girl_id": {"$in": [x["_id"] async for x in db[c.GIRLS].find({"group_id": g["_id"]}, {"_id": 1})]}}),
                         "next_level": "girl"})
    elif level == "volunteer":
        q: dict = {"role": "volunteer", "is_active": True}
        if parent_id:
            q["village_ids"] = oid(parent_id)
        async for u in db[c.USERS].find(q).sort("name", 1):
            # Within a village drill-down, count only that village's work.
            summary_ = await metrics.activity_summary(db, u["_id"], oid(parent_id) if parent_id else None, start, upto)
            rows.append({"id": str(u["_id"]), "name": u["name"], "village_id": str(u.get("village_id")), **summary_,
                         "next_level": "girl"})
    elif level == "girl":
        if not parent_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "parent_id (group, village or volunteer id) is required")
        pid = oid(parent_id)
        parent_vol = await db[c.USERS].find_one({"_id": pid, "role": "volunteer"})
        if parent_vol:
            q = {"village_id": {"$in": parent_vol.get("village_ids") or [parent_vol.get("village_id")]}}
        elif await db[c.GROUPS].find_one({"_id": pid}):
            q = {"group_id": pid}
        else:
            q = {"village_id": pid}
        async for g in db[c.GIRLS].find({**q, "is_deleted": {"$ne": True}}).sort("girl_seq", 1).limit(500):
            rows.append({"id": str(g["_id"]), "girl_code": g["girl_code"], "name": g.get("name"), "name_en": g.get("name_en"),
                         "household_head": (g.get("household") or {}).get("head_name"),
                         "father_name": (g.get("household") or {}).get("father_name"),
                         "school_status": g.get("school_status"),
                         "open_cases": (g.get("case_summary") or {}).get("open", 0),
                         "anaemia_status": (g.get("health_summary") or {}).get("anaemia_status"),
                         "last_participation_at": serialize(g.get("last_participation_at"))})
    return {"level": level, "parent_id": parent_id, "period_start": start, "period_end": end, "rows": rows}


@router.get("/past-vs-upcoming")
async def past_vs_upcoming(
    db: Db,
    _: Stakeholder,
    months_back: int = Query(6, ge=1, le=24),
    months_ahead: int = Query(3, ge=1, le=12),
    taluka_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
):
    """Historical trends alongside planned events, visits and targets."""
    vids = await _village_scope(db, taluka_id, village_id)
    today = today_local()
    past_start = (today.replace(day=1) - timedelta(days=31 * (months_back - 1))).replace(day=1)
    past = await activity.timeseries(db, past_start, today, "monthly", village_ids=vids)

    ahead_end = today
    for _i in range(months_ahead):
        ahead_end = period_bounds("monthly", ahead_end + timedelta(days=1))[1]
    tomorrow = today + timedelta(days=1)
    ls, le = local_day_bounds(tomorrow, ahead_end)
    upcoming: dict = {}
    async for ev in db[c.EVENTS].find({"status": "scheduled", "start_at": {"$gte": ls, "$lt": le}, **_vmatch(vids)},
                                      {"start_at": 1, "event_type": 1}):
        k = activity.bucket_key(ev["start_at"].date(), "monthly")
        upcoming.setdefault(k, {"events_planned": 0, "visits_planned": 0, "targets_starting": 0, "target_value_total": 0})
        upcoming[k]["events_planned"] += 1
    async for hv in db[c.HOME_VISITS].find({"status": "planned", "visit_date": {"$gte": to_dt(tomorrow), "$lte": to_dt(ahead_end)},
                                            **_vmatch(vids)}, {"visit_date": 1}):
        k = activity.bucket_key(hv["visit_date"].date(), "monthly")
        upcoming.setdefault(k, {"events_planned": 0, "visits_planned": 0, "targets_starting": 0, "target_value_total": 0})
        upcoming[k]["visits_planned"] += 1
    async for t in db[c.TARGETS].find({"status": "active", "period_start": {"$gte": to_dt(tomorrow), "$lte": to_dt(ahead_end)},
                                       **_vmatch(vids)}, {"period_start": 1, "target_value": 1}):
        k = activity.bucket_key(t["period_start"].date(), "monthly")
        upcoming.setdefault(k, {"events_planned": 0, "visits_planned": 0, "targets_starting": 0, "target_value_total": 0})
        upcoming[k]["targets_starting"] += 1
        upcoming[k]["target_value_total"] += t["target_value"]
    future_keys = activity.bucket_keys(tomorrow, ahead_end, "monthly")
    empty = {"events_planned": 0, "visits_planned": 0, "targets_starting": 0, "target_value_total": 0}
    due_cases = await db[c.CASES].count_documents({"status": {"$in": OPEN_CASE_STATUSES},
                                                   "due_date": {"$gte": to_dt(tomorrow), "$lte": to_dt(ahead_end)}, **_vmatch(vids)})
    return {
        "past": past,
        "upcoming": [{"period": k, **upcoming.get(k, empty)} for k in future_keys],
        "case_follow_ups_due": due_cases,
        "today": today,
    }
