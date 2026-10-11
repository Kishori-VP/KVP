"""Report builders (PRD 4.14). Each returns the report dict understood by exporters."""

import re
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.services import activity, metrics
from app.services.beneficiaries import OPEN_CASE_STATUSES
from app.services.events import display_status, local_day_bounds, summarize_attendance
from app.services.targets import with_progress
from app.utils.dates import (
    PeriodType,
    day_range,
    local_tz,
    next_period,
    period_bounds,
    previous_period,
    to_dt,
    today_local,
    utcnow,
)

REPORT_TYPES = {
    "programme_summary": "Programme summary (KPIs vs previous period)",
    "village_wise": "Village-wise activity report",
    "taluka_wise": "Taluka-wise activity report",
    "volunteer_wise": "Volunteer-wise activity and target report",
    "activity_wise": "Activity / event-type report",
    "home_visits": "House-visit report",
    "beneficiary_coverage": "Beneficiary coverage report",
    "event_completion": "Event completion and attendance report",
    "target_achievement": "Target vs achievement report",
    "past_vs_upcoming": "Past period vs upcoming plans",
    "case_ageing": "Case ageing and resolution report",
    "participation": "Girls' participation and attendance report",
    "health": "Health / anaemia coverage report",
    "donor_summary": "Donor / management summary",
}


def col(key: str, label: str) -> dict:
    return {"key": key, "label": label}


def resolve_period(period: PeriodType, reference: date | None, start: date | None, end: date | None) -> tuple[date, date, str]:
    if period == "custom":
        if not (start and end) or end < start:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Custom reports need a valid start_date and end_date")
        s, e = start, end
    else:
        s, e = period_bounds(period, reference)
    label = s.strftime("%d %b %Y") if s == e else f"{s:%d %b %Y} – {e:%d %b %Y}"
    return s, e, f"{period.title()}: {label}"


async def _scope_villages(db, taluka_id=None, village_id=None) -> list[dict]:
    q: dict = {"status": "active"}
    if village_id:
        q["_id"] = village_id
    elif taluka_id:
        q["taluka_id"] = taluka_id
    return await db[c.VILLAGES].find(q).sort("name", 1).to_list()


def _totals(rows: list[dict], keys: list[str]) -> dict:
    return {k: sum((r.get(k) or 0) for r in rows) for k in keys}


async def _lookup_labels(db, type_: str) -> dict:
    return {d["code"]: d["label"] async for d in db[c.LOOKUPS].find({"type": type_})}


# ---------------------------------------------------------------- builders

async def programme_summary(db, start, end, period, scope):
    upto = min(end, today_local())
    prev_s, prev_e = previous_period(period, start) if period != "custom" else (start - (end - start) - timedelta(days=1), start - timedelta(days=1))
    vids = [v["_id"] for v in scope["villages"]]
    cur, prev = defaultdict(int), defaultdict(int)
    for vid in vids:
        for k, v in (await metrics.activity_summary(db, None, vid, start, upto)).items():
            cur[k] += v
        for k, v in (await metrics.activity_summary(db, None, vid, prev_s, prev_e)).items():
            prev[k] += v
    ls, le = local_day_bounds(start, end)
    girls = await db[c.GIRLS].count_documents({"village_id": {"$in": vids}, "is_deleted": {"$ne": True}})
    labels = {"home_visits": "Home visits", "group_meetings": "Group meetings", "events": "Events conducted",
              "event_attendance": "Event attendance (girls)", "girls_covered": "Girls reached",
              "follow_ups": "Follow-ups", "case_closures": "Cases resolved", "health_screenings": "Health screenings",
              "activity_reports": "Daily reports submitted"}
    rows = [{"indicator": label, "current": cur[k], "previous": prev[k], "change": cur[k] - prev[k],
             "change_pct": round(100 * (cur[k] - prev[k]) / prev[k], 1) if prev[k] else None}
            for k, label in labels.items()]
    summary = [
        {"label": "Girls registered", "value": girls},
        {"label": "Villages", "value": len(vids)},
        {"label": "Kishori Groups", "value": await db[c.GROUPS].count_documents({"village_id": {"$in": vids}, "group_type": "kishori", "is_active": True})},
        {"label": "Active volunteers", "value": await db[c.USERS].count_documents({"village_id": {"$in": vids}, "role": "volunteer", "is_active": True})},
        {"label": "Events planned in period", "value": await db[c.EVENTS].count_documents({"village_id": {"$in": vids}, "planned": True, "start_at": {"$gte": ls, "$lt": le}})},
        {"label": "Open cases (now)", "value": await db[c.CASES].count_documents({"village_id": {"$in": vids}, "status": {"$in": OPEN_CASE_STATUSES}})},
    ]
    return {"summary": summary, "sections": [{"title": "Activity vs previous period", "columns": [
        col("indicator", "Indicator"), col("current", "This period"), col("previous", f"Previous ({prev_s:%d %b} – {prev_e:%d %b})"),
        col("change", "Change"), col("change_pct", "Change %")], "rows": rows}]}


async def _village_rows(db, villages, start, end) -> list[dict]:
    upto = min(end, today_local())
    statuses = await activity.village_activity_status(db)
    taluka_names = {t["_id"]: t["name"] async for t in db[c.TALUKAS].find({}, {"name": 1})}
    rows = []
    for v in villages:
        m = await metrics.activity_summary(db, None, v["_id"], start, upto)
        rows.append({
            "village": v["name"], "village_mr": v.get("name_mr"), "taluka": taluka_names.get(v["taluka_id"]),
            "girls": await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True}}),
            "groups": await db[c.GROUPS].count_documents({"village_id": v["_id"], "group_type": "kishori", "is_active": True}),
            **m,
            "open_cases": await db[c.CASES].count_documents({"village_id": v["_id"], "status": {"$in": OPEN_CASE_STATUSES}}),
            "activity_status": statuses.get(v["_id"], {}).get("status"),
        })
    return rows


VILLAGE_COLS = [col("girls", "Girls"), col("groups", "Groups"), col("home_visits", "Home visits"),
                col("group_meetings", "Meetings"), col("events", "Events"), col("event_attendance", "Attendance"),
                col("girls_covered", "Girls reached"), col("open_cases", "Open cases")]
SUM_KEYS = ["girls", "groups", "home_visits", "group_meetings", "events", "event_attendance", "girls_covered", "open_cases"]


async def village_wise(db, start, end, period, scope):
    rows = await _village_rows(db, scope["villages"], start, end)
    return {"summary": [], "sections": [{"title": "Village-wise", "columns": [
        col("village", "Village"), col("village_mr", "गाव"), col("taluka", "Taluka"), *VILLAGE_COLS,
        col("activity_status", "Status")], "rows": rows, "totals": _totals(rows, SUM_KEYS)}]}


async def taluka_wise(db, start, end, period, scope):
    rows = await _village_rows(db, scope["villages"], start, end)
    agg: dict = {}
    for r in rows:
        t = agg.setdefault(r["taluka"], {"taluka": r["taluka"], "villages": 0, **{k: 0 for k in SUM_KEYS}})
        t["villages"] += 1
        for k in SUM_KEYS:
            t[k] += r.get(k) or 0
    out = sorted(agg.values(), key=lambda x: x["taluka"] or "")
    return {"summary": [], "sections": [{"title": "Taluka-wise", "columns": [
        col("taluka", "Taluka"), col("villages", "Villages"), *VILLAGE_COLS], "rows": out,
        "totals": _totals(out, ["villages", *SUM_KEYS])}]}


async def volunteer_wise(db, start, end, period, scope):
    vids = [v["_id"] for v in scope["villages"]]
    vols = await db[c.USERS].find({"role": "volunteer", "is_active": True, "village_id": {"$in": vids}}).sort("name", 1).to_list()
    vnames = {v["_id"]: v["name"] for v in scope["villages"]}
    upto = min(end, today_local())
    rows = []
    for u in vols:
        m = await metrics.activity_summary(db, u["_id"], u.get("village_id"), start, upto)
        targets = await with_progress(db, await db[c.TARGETS].find({
            "volunteer_id": u["_id"], "status": "active", "period_start": {"$lte": to_dt(end)},
            "period_end": {"$gte": to_dt(start)}}).to_list())
        pcts = [min(t["progress"]["progress_pct"], 100) for t in targets]
        rows.append({"volunteer": u["name"], "phone": u["phone"], "village": vnames.get(u.get("village_id")), **m,
                     "targets": len(targets), "avg_achievement_pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
                     "targets_missed": sum(1 for t in targets if t["progress"]["status"] == "missed")})
    return {"summary": [], "sections": [{"title": "Volunteer-wise", "columns": [
        col("volunteer", "Volunteer"), col("village", "Village"), col("home_visits", "Home visits"),
        col("group_meetings", "Meetings"), col("events", "Events"), col("girls_covered", "Girls reached"),
        col("follow_ups", "Follow-ups"), col("case_closures", "Cases resolved"), col("activity_reports", "Daily reports"),
        col("targets", "Targets"), col("avg_achievement_pct", "Avg achievement %"), col("targets_missed", "Missed")],
        "rows": rows}]}


async def activity_wise(db, start, end, period, scope):
    vids = [v["_id"] for v in scope["villages"]]
    ls, le = local_day_bounds(start, end)
    labels = await _lookup_labels(db, "event_type")
    agg: dict = {}
    async for ev in db[c.EVENTS].find({"village_id": {"$in": vids}, "start_at": {"$gte": ls, "$lt": le}}):
        r = agg.setdefault(ev["event_type"], {"activity": labels.get(ev["event_type"], ev["event_type"]),
                                              "planned": 0, "conducted": 0, "cancelled": 0, "pending": 0,
                                              "girls_attended": 0, "villages": set()})
        r["planned"] += 1 if ev.get("planned") else 0
        r["villages"].add(ev["village_id"])
        if ev["status"] == "completed":
            r["conducted"] += 1
            r["girls_attended"] += summarize_attendance(ev)["girls_present"]
        elif ev["status"] == "cancelled":
            r["cancelled"] += 1
        else:
            r["pending"] += 1
    rows = [{**r, "villages": len(r["villages"])} for r in agg.values()]
    # Activities captured through daily reports (Google-Form style).
    act_labels = await _lookup_labels(db, "activity_type")
    s, e = day_range(start, end)
    rep: dict = defaultdict(int)
    async for r in db[c.ACTIVITY_REPORTS].find({"village_id": {"$in": vids}, "report_date": {"$gte": s, "$lt": e}}, {"activities": 1}):
        for a in r.get("activities", []):
            rep[a] += 1
    rep_rows = [{"activity": act_labels.get(k, k), "days_reported": v} for k, v in sorted(rep.items(), key=lambda x: -x[1])]
    return {"summary": [], "sections": [
        {"title": "Events by type", "columns": [col("activity", "Event type"), col("planned", "Planned"),
                                                col("conducted", "Conducted"), col("pending", "Pending/overdue"),
                                                col("cancelled", "Cancelled"), col("girls_attended", "Girls attended"),
                                                col("villages", "Villages")],
         "rows": rows, "totals": _totals(rows, ["planned", "conducted", "pending", "cancelled", "girls_attended"])},
        {"title": "Activities in daily reports", "columns": [col("activity", "Activity"), col("days_reported", "Days reported")],
         "rows": rep_rows},
    ]}


async def home_visits_report(db, start, end, period, scope):
    vids = [v["_id"] for v in scope["villages"]]
    vnames = {v["_id"]: v["name"] for v in scope["villages"]}
    users = {u["_id"]: u["name"] async for u in db[c.USERS].find({}, {"name": 1})}
    s, e = day_range(start, end)
    rows = []
    async for h in db[c.HOME_VISITS].find({"village_id": {"$in": vids}, "visit_date": {"$gte": s, "$lt": e}}).sort("visit_date", 1):
        codes = [g["girl_code"] async for g in db[c.GIRLS].find({"_id": {"$in": h.get("girl_ids", [])}}, {"girl_code": 1})]
        risks = [k for k, v in (h.get("risk_indicators") or {}).items() if v is True]
        rows.append({"date": h["visit_date"].date(), "volunteer": users.get(h["volunteer_id"]), "village": vnames.get(h["village_id"]),
                     "status": h["status"], "purpose": h["purpose"], "girls": codes, "risks": risks,
                     "observations": (h.get("observations") or "")[:200], "gps": "Yes" if h.get("gps") else "No"})
    per_village = []
    upto = min(end, today_local())
    for v in scope["villages"]:
        per_village.append({"village": v["name"], "home_visits": await metrics.home_visits(db, None, v["_id"], start, upto)})
    return {"summary": [{"label": "Visit records", "value": len(rows)},
                        {"label": "Completed", "value": sum(1 for r in rows if r["status"] == "completed")},
                        {"label": "Planned", "value": sum(1 for r in rows if r["status"] == "planned")},
                        {"label": "Missed", "value": sum(1 for r in rows if r["status"] == "missed")},
                        {"label": "Total home visits (incl. daily reports)", "value": sum(r["home_visits"] for r in per_village)}],
            "sections": [
                {"title": "Home visits by village", "columns": [col("village", "Village"), col("home_visits", "Home visits")],
                 "rows": per_village, "totals": _totals(per_village, ["home_visits"])},
                {"title": "Visit records", "columns": [col("date", "Date"), col("volunteer", "Volunteer"), col("village", "Village"),
                                                       col("status", "Status"), col("purpose", "Purpose"), col("girls", "Girl IDs"),
                                                       col("risks", "Risk flags"), col("observations", "Observations"), col("gps", "GPS")],
                 "rows": rows},
            ]}


async def beneficiary_coverage(db, start, end, period, scope):
    upto = min(end, today_local())
    rows = []
    for v in scope["villages"]:
        total = await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True}})
        reached = await metrics.girls_covered_ids(db, None, v["_id"], start, upto)
        ever = await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True},
                                                  "last_participation_at": {"$ne": None}})
        no_group = await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True}, "group_id": None})
        rows.append({"village": v["name"], "girls": total, "reached_in_period": len(reached),
                     "coverage_pct": round(100 * len(reached) / total, 1) if total else None,
                     "ever_participated": ever, "never_participated": total - ever, "not_in_group": no_group})
    t = _totals(rows, ["girls", "reached_in_period", "ever_participated", "never_participated", "not_in_group"])
    t["coverage_pct"] = round(100 * t["reached_in_period"] / t["girls"], 1) if t["girls"] else None
    return {"summary": [{"label": "Girls registered", "value": t["girls"]},
                        {"label": "Girls reached in period", "value": t["reached_in_period"]},
                        {"label": "Coverage %", "value": t["coverage_pct"]}],
            "sections": [{"title": "Coverage by village", "columns": [
                col("village", "Village"), col("girls", "Girls"), col("reached_in_period", "Reached"),
                col("coverage_pct", "Coverage %"), col("ever_participated", "Ever participated"),
                col("never_participated", "Never participated"), col("not_in_group", "Not in a group")],
                "rows": rows, "totals": t}]}


async def event_completion(db, start, end, period, scope):
    vids = [v["_id"] for v in scope["villages"]]
    vnames = {v["_id"]: v["name"] for v in scope["villages"]}
    users = {u["_id"]: u["name"] async for u in db[c.USERS].find({}, {"name": 1})}
    labels = await _lookup_labels(db, "event_type")
    ls, le = local_day_bounds(start, end)
    rows = []
    async for ev in db[c.EVENTS].find({"village_id": {"$in": vids}, "start_at": {"$gte": ls, "$lt": le}}).sort("start_at", 1):
        att = summarize_attendance(ev)
        rows.append({"date": ev["start_at"].astimezone(local_tz()).date(), "title": ev["title"],
                     "type": labels.get(ev["event_type"], ev["event_type"]), "village": vnames.get(ev["village_id"]),
                     "volunteer": users.get(ev.get("responsible_volunteer_id")), "status": display_status(ev),
                     "expected": att["expected"], "girls_present": att["girls_present"], "others": att["other_participants"],
                     "report": "Yes" if ev.get("report") else "No", "expenditure": (ev.get("expenditure") or {}).get("total")})
    by_status: dict = defaultdict(int)
    for r in rows:
        by_status[r["status"]] += 1
    return {"summary": [{"label": "Events in period", "value": len(rows)},
                        *[{"label": k.title(), "value": v} for k, v in sorted(by_status.items())],
                        {"label": "Girls attended (completed events)", "value": sum(r["girls_present"] for r in rows if r["status"] == "completed")}],
            "sections": [{"title": "Events", "columns": [
                col("date", "Date"), col("title", "Event"), col("type", "Type"), col("village", "Village"),
                col("volunteer", "Volunteer"), col("status", "Status"), col("expected", "Expected"),
                col("girls_present", "Girls present"), col("others", "Others"), col("report", "Report"),
                col("expenditure", "Spend (₹)")], "rows": rows,
                "totals": _totals(rows, ["expected", "girls_present", "others", "expenditure"])}]}


async def target_achievement(db, start, end, period, scope):
    vids = [v["_id"] for v in scope["villages"]]
    vnames = {v["_id"]: v["name"] for v in scope["villages"]}
    users = {u["_id"]: u["name"] async for u in db[c.USERS].find({}, {"name": 1})}
    targets = await db[c.TARGETS].find({"village_id": {"$in": vids}, "status": "active",
                                        "period_start": {"$lte": to_dt(end)}, "period_end": {"$gte": to_dt(start)}}).sort("period_start", 1).to_list()
    rows = [{"volunteer": users.get(t["volunteer_id"]), "village": vnames.get(t["village_id"]), "target": t["title"],
             "period": f"{t['period_start']:%d %b} – {t['period_end']:%d %b %Y}", "target_value": t["target_value"],
             "achieved": t["progress"]["achieved"], "progress_pct": t["progress"]["progress_pct"], "status": t["progress"]["status"],
             "revisions": len(t.get("revisions", []))}
            for t in await with_progress(db, targets)]
    by_status: dict = defaultdict(int)
    for r in rows:
        by_status[r["status"]] += 1
    return {"summary": [{"label": "Targets", "value": len(rows)},
                        *[{"label": k.replace("_", " ").title(), "value": v} for k, v in sorted(by_status.items())]],
            "sections": [{"title": "Targets", "columns": [
                col("volunteer", "Volunteer"), col("village", "Village"), col("target", "Target"), col("period", "Period"),
                col("target_value", "Target"), col("achieved", "Achieved"), col("progress_pct", "Progress %"),
                col("status", "Status"), col("revisions", "Revisions")], "rows": rows}]}


async def past_vs_upcoming(db, start, end, period, scope):
    """Past = the selected period; upcoming = the next period of the same length."""
    vids = [v["_id"] for v in scope["villages"]]
    if period == "custom":
        n_s, n_e = end + timedelta(days=1), end + (end - start) + timedelta(days=1)
    else:
        n_s, n_e = next_period(period, end)
    upto = min(end, today_local())
    past = defaultdict(int)
    for vid in vids:
        for k, v in (await metrics.activity_summary(db, None, vid, start, upto)).items():
            past[k] += v
    nls, nle = local_day_bounds(n_s, n_e)
    upcoming_events = await db[c.EVENTS].count_documents({"village_id": {"$in": vids}, "status": "scheduled", "start_at": {"$gte": nls, "$lt": nle}})
    upcoming_visits = await db[c.HOME_VISITS].count_documents({"village_id": {"$in": vids}, "status": "planned",
                                                               "visit_date": {"$gte": to_dt(n_s), "$lte": to_dt(n_e)}})
    ttypes = {d["code"]: d async for d in db[c.LOOKUPS].find({"type": "target_type"})}
    target_rows: dict = {}
    async for t in db[c.TARGETS].find({"village_id": {"$in": vids}, "status": "active",
                                       "period_start": {"$lte": to_dt(n_e)}, "period_end": {"$gte": to_dt(n_s)}}):
        metric = t["metric"]
        r = target_rows.setdefault(metric, {"metric": ttypes.get(t["target_type"], {}).get("label", metric),
                                            "past_actual": past.get(metric, 0), "upcoming_target": 0})
        r["upcoming_target"] += t["target_value"]
    ls, le = local_day_bounds(start, end)
    planned_past = await db[c.EVENTS].count_documents({"village_id": {"$in": vids}, "planned": True, "start_at": {"$gte": ls, "$lt": le}})
    rows = [
        {"item": "Events", "past": past["events"], "past_planned": planned_past, "upcoming_planned": upcoming_events},
        {"item": "Home visits", "past": past["home_visits"], "past_planned": None, "upcoming_planned": upcoming_visits},
        {"item": "Group meetings", "past": past["group_meetings"], "past_planned": None, "upcoming_planned": None},
        {"item": "Girls reached", "past": past["girls_covered"], "past_planned": None, "upcoming_planned": None},
    ]
    return {"summary": [{"label": "Past period", "value": f"{start:%d %b %Y} – {end:%d %b %Y}"},
                        {"label": "Upcoming period", "value": f"{n_s:%d %b %Y} – {n_e:%d %b %Y}"}],
            "sections": [
                {"title": "Past vs upcoming", "columns": [col("item", "Item"), col("past", "Past (actual)"),
                                                          col("past_planned", "Past (planned)"), col("upcoming_planned", "Upcoming (planned)")],
                 "rows": rows},
                {"title": "Upcoming targets vs past performance", "columns": [col("metric", "Target type"),
                    col("past_actual", "Past actual"), col("upcoming_target", "Upcoming target")],
                 "rows": list(target_rows.values())},
            ]}


AGE_BUCKETS = [(0, 7, "0-7 days"), (8, 30, "8-30 days"), (31, 90, "31-90 days"), (91, 10_000, "90+ days")]


async def case_ageing(db, start, end, period, scope):
    vids = [v["_id"] for v in scope["villages"]]
    labels = await _lookup_labels(db, "case_category")
    now = utcnow()
    open_rows: dict = {}
    async for cs in db[c.CASES].find({"village_id": {"$in": vids}, "status": {"$in": OPEN_CASE_STATUSES}}, {"timeline": 0}):
        age = (now - cs["opened_at"]).days
        r = open_rows.setdefault(cs["category"], {"category": labels.get(cs["category"], cs["category"]), "open": 0,
                                                  **{b[2]: 0 for b in AGE_BUCKETS}, "overdue": 0, "critical_high": 0})
        r["open"] += 1
        for lo, hi, name in AGE_BUCKETS:
            if lo <= age <= hi:
                r[name] += 1
        if cs.get("due_date") and cs["due_date"] < to_dt(today_local()):
            r["overdue"] += 1
        if cs["severity"] in ("critical", "high"):
            r["critical_high"] += 1
    s, e = day_range(start, end)
    resolved: dict = {}
    async for cs in db[c.CASES].find({"village_id": {"$in": vids}, "resolved_at": {"$gte": s, "$lt": e}}, {"timeline": 0}):
        r = resolved.setdefault(cs["category"], {"category": labels.get(cs["category"], cs["category"]), "resolved": 0, "_days": []})
        r["resolved"] += 1
        r["_days"].append((cs["resolved_at"] - cs["opened_at"]).days)
    res_rows = [{"category": r["category"], "resolved": r["resolved"],
                 "avg_days_to_resolve": round(sum(r["_days"]) / len(r["_days"]), 1),
                 "max_days": max(r["_days"])} for r in resolved.values()]
    opened = await db[c.CASES].count_documents({"village_id": {"$in": vids}, "opened_at": {"$gte": s, "$lt": e}})
    orows = list(open_rows.values())
    return {"summary": [{"label": "Cases opened in period", "value": opened},
                        {"label": "Cases resolved in period", "value": sum(r["resolved"] for r in res_rows)},
                        {"label": "Open cases now", "value": sum(r["open"] for r in orows)},
                        {"label": "Overdue open cases", "value": sum(r["overdue"] for r in orows)}],
            "sections": [
                {"title": "Open case ageing", "columns": [col("category", "Category"), col("open", "Open"),
                    *[col(b[2], b[2]) for b in AGE_BUCKETS], col("overdue", "Overdue"), col("critical_high", "Critical/High")],
                 "rows": orows, "totals": _totals(orows, ["open", *[b[2] for b in AGE_BUCKETS], "overdue", "critical_high"])},
                {"title": "Resolution in period", "columns": [col("category", "Category"), col("resolved", "Resolved"),
                    col("avg_days_to_resolve", "Avg days to resolve"), col("max_days", "Max days")], "rows": res_rows},
            ]}


async def participation(db, start, end, period, scope):
    ls, le = local_day_bounds(start, end)
    rows = []
    for v in scope["villages"]:
        girls = await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True}})
        events = await db[c.EVENTS].find({"village_id": v["_id"], "status": "completed", "start_at": {"$gte": ls, "$lt": le}},
                                         {"attendance": 1, "other_participants": 1, "expected_participants": 1}).to_list()
        attended: dict = defaultdict(int)
        recorded = 0
        for ev in events:
            for a in ev.get("attendance", []):
                recorded += 1
                if a.get("present"):
                    attended[a["girl_id"]] += 1
        present = sum(attended.values())
        rows.append({"village": v["name"], "girls": girls, "events": len(events), "attendance_records": recorded,
                     "present": present, "attendance_rate_pct": round(100 * present / recorded, 1) if recorded else None,
                     "distinct_girls_attended": len(attended),
                     "girls_attending_pct": round(100 * len(attended) / girls, 1) if girls else None,
                     "regular_attendees": sum(1 for n in attended.values() if n >= 3)})
    s, e = day_range(start, end)
    meet_part = 0
    async for r in db[c.ACTIVITY_REPORTS].find({"village_id": {"$in": [v["_id"] for v in scope["villages"]]},
                                                "report_date": {"$gte": s, "$lt": e}}, {"girls_present": 1}):
        meet_part += r.get("girls_present") or 0
    return {"summary": [{"label": "Group-meeting participation (daily reports)", "value": meet_part},
                        {"label": "Girls attending events", "value": sum(r["distinct_girls_attended"] for r in rows)}],
            "sections": [{"title": "Participation by village", "columns": [
                col("village", "Village"), col("girls", "Girls"), col("events", "Events"), col("present", "Attendances"),
                col("attendance_rate_pct", "Attendance rate %"), col("distinct_girls_attended", "Distinct girls"),
                col("girls_attending_pct", "% of girls"), col("regular_attendees", "Attended 3+")],
                "rows": rows, "totals": _totals(rows, ["girls", "events", "present", "distinct_girls_attended", "regular_attendees"])}]}


async def health(db, start, end, period, scope):
    s, e = day_range(start, end)
    rows = []
    for v in scope["villages"]:
        girls = await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True}})
        screened_ever = await db[c.GIRLS].count_documents({"village_id": v["_id"], "is_deleted": {"$ne": True},
                                                           "health_summary.latest_hb": {"$ne": None}})
        dist: dict = defaultdict(int)
        async for g in db[c.GIRLS].find({"village_id": v["_id"], "health_summary.anaemia_status": {"$ne": None}},
                                        {"health_summary.anaemia_status": 1}):
            dist[g["health_summary"]["anaemia_status"]] += 1
        in_period = await db[c.HEALTH_RECORDS].distinct("girl_id", {"village_id": v["_id"], "recorded_on": {"$gte": s, "$lt": e}})
        rows.append({"village": v["name"], "girls": girls, "screened_in_period": len(in_period),
                     "screened_ever": screened_ever,
                     "coverage_pct": round(100 * screened_ever / girls, 1) if girls else None,
                     "normal": dist["normal"], "mild": dist["mild"], "moderate": dist["moderate"], "severe": dist["severe"]})
    t = _totals(rows, ["girls", "screened_in_period", "screened_ever", "normal", "mild", "moderate", "severe"])
    anaemic = t["mild"] + t["moderate"] + t["severe"]
    # Monthly trend of average Hb across the period.
    trend: dict = defaultdict(list)
    async for r in db[c.HEALTH_RECORDS].find({"village_id": {"$in": [v["_id"] for v in scope["villages"]]},
                                              "recorded_on": {"$gte": s, "$lt": e}, "hb_level": {"$ne": None}},
                                             {"recorded_on": 1, "hb_level": 1, "anaemia_status": 1}):
        trend[r["recorded_on"].strftime("%Y-%m")].append(r)
    trend_rows = [{"month": k, "screenings": len(v), "avg_hb": round(sum(x["hb_level"] for x in v) / len(v), 2),
                   "anaemic_pct": round(100 * sum(1 for x in v if x.get("anaemia_status") != "normal") / len(v), 1)}
                  for k, v in sorted(trend.items())]
    return {"summary": [{"label": "Girls screened (ever)", "value": t["screened_ever"]},
                        {"label": "Screening coverage %", "value": round(100 * t["screened_ever"] / t["girls"], 1) if t["girls"] else None},
                        {"label": "Anaemia prevalence % (latest Hb)", "value": round(100 * anaemic / t["screened_ever"], 1) if t["screened_ever"] else None}],
            "sections": [
                {"title": "Anaemia by village", "columns": [col("village", "Village"), col("girls", "Girls"),
                    col("screened_in_period", "Screened in period"), col("screened_ever", "Screened (ever)"),
                    col("coverage_pct", "Coverage %"), col("normal", "Normal"), col("mild", "Mild"),
                    col("moderate", "Moderate"), col("severe", "Severe")], "rows": rows, "totals": t},
                {"title": "Monthly trend", "columns": [col("month", "Month"), col("screenings", "Screenings"),
                    col("avg_hb", "Average Hb"), col("anaemic_pct", "Anaemic %")], "rows": trend_rows},
            ]}


async def donor_summary(db, start, end, period, scope):
    """Mirrors the existing monthly donor report layout."""
    vids = [v["_id"] for v in scope["villages"]]
    upto = min(end, today_local())
    ls, le = local_day_bounds(start, end)
    s, e = day_range(start, end)
    rows = await _village_rows(db, scope["villages"], start, end)
    meet_part = 0
    async for r in db[c.ACTIVITY_REPORTS].find({"village_id": {"$in": vids}, "report_date": {"$gte": s, "$lt": e}}, {"girls_present": 1}):
        meet_part += r.get("girls_present") or 0
    by_type = defaultdict(lambda: {"events": 0, "girls": 0, "villages": set()})
    async for ev in db[c.EVENTS].find({"village_id": {"$in": vids}, "status": "completed", "start_at": {"$gte": ls, "$lt": le}}):
        b = by_type[ev["event_type"]]
        b["events"] += 1
        b["girls"] += summarize_attendance(ev)["girls_present"]
        b["villages"].add(ev["village_id"])
    labels = await _lookup_labels(db, "event_type")
    highlights = [{"activity": labels.get(k, k), "events": v["events"], "girls": v["girls"], "villages": len(v["villages"])}
                  for k, v in sorted(by_type.items(), key=lambda x: -x[1]["events"])]
    girls_reached = sum(r["girls_covered"] for r in rows)
    return {
        "summary": [
            {"label": "Girls registered", "value": sum(r["girls"] for r in rows)},
            {"label": "Girls reached", "value": girls_reached},
            {"label": "Villages covered", "value": len(vids)},
            {"label": "Kishori Groups", "value": sum(r["groups"] for r in rows)},
            {"label": "Group meetings conducted", "value": sum(r["group_meetings"] for r in rows)},
            {"label": "Group-meeting participation", "value": meet_part},
            {"label": "Home visits", "value": sum(r["home_visits"] for r in rows)},
            {"label": "Events conducted", "value": sum(r["events"] for r in rows)},
            {"label": "Cases resolved", "value": sum(r["case_closures"] for r in rows)},
        ],
        "sections": [
            {"title": "What happened this period", "columns": [col("activity", "Activity"), col("events", "Sessions"),
                col("girls", "Girls participated"), col("villages", "Villages")], "rows": highlights},
            {"title": "Village detail", "columns": [col("village", "Village"), col("girls", "Girls"),
                col("girls_covered", "Girls reached"), col("groups", "Groups"), col("group_meetings", "Group meetings"),
                col("home_visits", "Home visits"), col("events", "Events")], "rows": rows,
             "totals": _totals(rows, ["girls", "girls_covered", "groups", "group_meetings", "home_visits", "events"])},
        ],
        "notes": ["Figures are computed from records captured in the KVP system for the period, including "
                  "back-dated historical entries. Girls reached = distinct girls in home visits or event attendance.",
                  "AI-generated narrative is not included; summaries require human review before sharing with donors."],
    }


BUILDERS = {
    "programme_summary": programme_summary,
    "village_wise": village_wise,
    "taluka_wise": taluka_wise,
    "volunteer_wise": volunteer_wise,
    "activity_wise": activity_wise,
    "home_visits": home_visits_report,
    "beneficiary_coverage": beneficiary_coverage,
    "event_completion": event_completion,
    "target_achievement": target_achievement,
    "past_vs_upcoming": past_vs_upcoming,
    "case_ageing": case_ageing,
    "participation": participation,
    "health": health,
    "donor_summary": donor_summary,
}


async def build_report(db: AsyncDatabase, report_type: str, period: PeriodType, reference: date | None = None,
                       start: date | None = None, end: date | None = None, taluka_id=None, village_id=None) -> dict:
    if report_type not in BUILDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown report type. Available: {list(REPORT_TYPES)}")
    s, e, label = resolve_period(period, reference, start, end)
    villages = await _scope_villages(db, taluka_id, village_id)
    scope_label = "All villages"
    if village_id and villages:
        scope_label = f"Village: {villages[0]['name']}"
    elif taluka_id:
        t = await db[c.TALUKAS].find_one({"_id": taluka_id})
        scope_label = f"Taluka: {t['name'] if t else '?'}"
    body = await BUILDERS[report_type](db, s, e, period, {"villages": villages})
    for section in body.get("sections", []):
        section.setdefault("key", section_key(section["title"]))
    return {
        "report_type": report_type,
        "title": REPORT_TYPES[report_type],
        "subtitle": scope_label,
        "period": {"start": s, "end": e, "label": label, "type": period},
        "summary": body.get("summary", []),
        "sections": body.get("sections", []),
        "notes": body.get("notes", []),
    }


def section_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def report_structure(report: dict) -> dict:
    """Section keys, columns and summary labels a template can choose from."""
    return {
        "report_type": report["report_type"],
        "summary_labels": [s["label"] for s in report["summary"]],
        "sections": [{"key": s["key"], "title": s["title"], "columns": s["columns"]} for s in report["sections"]],
    }


def validate_template_against(structure: dict, tpl: dict) -> list[str]:
    errors = []
    labels = set(structure["summary_labels"])
    for label in tpl.get("summary_labels") or []:
        if label not in labels:
            errors.append(f"Unknown summary item '{label}'. Available: {sorted(labels)}")
    sections = {s["key"]: s for s in structure["sections"]}
    for sel in tpl.get("sections") or []:
        sec = sections.get(sel["key"])
        if not sec:
            errors.append(f"Unknown section '{sel['key']}'. Available: {sorted(sections)}")
            continue
        cols = {c["key"] for c in sec["columns"]}
        for col_key in sel.get("columns") or []:
            if col_key not in cols:
                errors.append(f"Section '{sel['key']}' has no column '{col_key}'. Available: {sorted(cols)}")
    return errors


def apply_template(report: dict, tpl: dict) -> dict:
    """Shape a built report with a saved template: title, summary items, sections, columns, notes."""
    out = dict(report)
    out["template_id"] = tpl.get("_id")
    out["template_name"] = tpl["name"]
    if tpl.get("title"):
        out["title"] = tpl["title"]
    if tpl.get("subtitle_note"):
        out["subtitle"] = f"{report['subtitle']} · {tpl['subtitle_note']}"
    if not tpl.get("include_summary", True):
        out["summary"] = []
    elif tpl.get("summary_labels"):
        order = {label: i for i, label in enumerate(tpl["summary_labels"])}
        out["summary"] = sorted((s for s in report["summary"] if s["label"] in order), key=lambda s: order[s["label"]])
    if tpl.get("sections"):
        by_key = {s["key"]: s for s in report["sections"]}
        sections = []
        for sel in tpl["sections"]:
            sec = by_key.get(sel["key"])
            if not sec:
                continue
            sec = dict(sec)
            if sel.get("title"):
                sec["title"] = sel["title"]
            if sel.get("columns"):
                cols = {c["key"]: c for c in sec["columns"]}
                sec["columns"] = [cols[k] for k in sel["columns"] if k in cols]
                if sec.get("totals"):
                    sec["totals"] = {k: v for k, v in sec["totals"].items() if k in sel["columns"]}
            sections.append(sec)
        out["sections"] = sections
    notes = list(tpl.get("notes") or [])
    out["notes"] = notes + (report["notes"] if tpl.get("append_default_notes", True) else [])
    return out
