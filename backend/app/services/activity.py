"""Time-bucketed field activity and recency, shared by volunteer and stakeholder dashboards."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.services.app_settings import get_setting
from app.services.events import local_day_bounds
from app.services.metrics import NOT_REJECTED, meeting_event_types
from app.utils.dates import day_range, local_tz, today_local

Unit = Literal["daily", "weekly", "monthly"]


def bucket_key(d: date, unit: Unit) -> str:
    if unit == "daily":
        return d.isoformat()
    if unit == "weekly":
        return (d - timedelta(days=d.weekday())).isoformat()
    return d.strftime("%Y-%m")


def bucket_keys(start: date, end: date, unit: Unit) -> list[str]:
    keys, d = [], start
    while d <= end:
        k = bucket_key(d, unit)
        if not keys or keys[-1] != k:
            keys.append(k)
        d += timedelta(days=1)
    return keys


def _scope(volunteer_id, village_ids, vol_field="volunteer_id") -> dict:
    q: dict = {}
    if volunteer_id:
        q[vol_field] = volunteer_id
    if village_ids is not None:
        q["village_id"] = {"$in": list(village_ids)}
    return q


async def timeseries(db: AsyncDatabase, start: date, end: date, unit: Unit,
                     volunteer_id=None, village_ids=None) -> list[dict]:
    s, e = day_range(start, end)
    ls, le = local_day_bounds(start, end)
    buckets: dict = defaultdict(lambda: defaultdict(int))
    visit_days = set()

    async for v in db[c.HOME_VISITS].find({**_scope(volunteer_id, village_ids), "status": "completed",
                                           "visit_date": {"$gte": s, "$lt": e}, **NOT_REJECTED},
                                          {"visit_date": 1, "volunteer_id": 1}):
        d = v["visit_date"].date()
        visit_days.add((v["volunteer_id"], d))
        buckets[bucket_key(d, unit)]["home_visits"] += 1

    meeting_types = set(await meeting_event_types(db))
    meeting_days = set()
    async for ev in db[c.EVENTS].find({**_scope(volunteer_id, village_ids, "responsible_volunteer_id"),
                                       "start_at": {"$gte": ls, "$lt": le}},
                                      {"start_at": 1, "status": 1, "event_type": 1, "attendance": 1,
                                       "responsible_volunteer_id": 1, "planned": 1, "end_at": 1}):
        d = ev["start_at"].astimezone(local_tz()).date()
        b = buckets[bucket_key(d, unit)]
        if ev.get("planned"):
            b["events_planned"] += 1
        if ev["status"] == "completed":
            b["events_completed"] += 1
            b["attendance"] += sum(1 for a in ev.get("attendance", []) if a.get("present"))
            if ev["event_type"] in meeting_types:
                b["group_meetings"] += 1
                meeting_days.add((ev.get("responsible_volunteer_id"), d))
        elif ev["status"] == "cancelled":
            b["events_cancelled"] += 1

    async for r in db[c.ACTIVITY_REPORTS].find({**_scope(volunteer_id, village_ids), "report_date": {"$gte": s, "$lt": e},
                                                **NOT_REJECTED},
                                               {"report_date": 1, "volunteer_id": 1, "home_visits_count": 1,
                                                "group_ids": 1, "girls_present": 1}):
        d = r["report_date"].date()
        b = buckets[bucket_key(d, unit)]
        b["activity_reports"] += 1
        if (r["volunteer_id"], d) not in visit_days:
            b["home_visits"] += r.get("home_visits_count") or 0
        if (r["volunteer_id"], d) not in meeting_days:
            b["group_meetings"] += len(r.get("group_ids") or [])
            b["meeting_participation"] += r.get("girls_present") or 0

    async for case in db[c.CASES].find({**_scope(None, village_ids), "opened_at": {"$gte": s, "$lt": e}},
                                       {"opened_at": 1}):
        buckets[bucket_key(case["opened_at"].astimezone(local_tz()).date(), unit)]["cases_opened"] += 1

    fields = ["home_visits", "group_meetings", "meeting_participation", "events_planned", "events_completed",
              "events_cancelled", "attendance", "activity_reports", "cases_opened"]
    return [{"period": k, **{f: buckets[k][f] for f in fields}} for k in bucket_keys(start, end, unit)]


async def last_activity_by_village(db: AsyncDatabase) -> dict:
    """village_id -> most recent field activity date (visit, report or completed event)."""
    last: dict = {}

    async def merge(coll, field, match, tz_local=False):
        pipeline = [{"$match": match}, {"$group": {"_id": "$village_id", "last": {"$max": f"${field}"}}}]
        async for row in await db[coll].aggregate(pipeline):
            d = row["last"].astimezone(local_tz()).date() if tz_local else row["last"].date()
            if row["_id"] and (row["_id"] not in last or d > last[row["_id"]]):
                last[row["_id"]] = d

    today_end = day_range(today_local(), today_local())[1]
    await merge(c.HOME_VISITS, "visit_date", {"status": "completed", "visit_date": {"$lt": today_end}})
    await merge(c.ACTIVITY_REPORTS, "report_date", {})
    await merge(c.EVENTS, "start_at", {"status": "completed"}, tz_local=True)
    return last


async def village_activity_status(db: AsyncDatabase) -> dict:
    """village_id -> {status, last_activity, days_since}"""
    rules = await get_setting(db, "village_status")
    last = await last_activity_by_village(db)
    today = today_local()
    out = {}
    async for v in db[c.VILLAGES].find({"status": "active"}, {"_id": 1}):
        d = last.get(v["_id"])
        days = (today - d).days if d else None
        if days is not None and days <= rules["on_track_within_days"]:
            state = "on_track"
        elif days is not None and days <= rules["delayed_within_days"]:
            state = "delayed"
        else:
            state = "no_recent_activity"
        out[v["_id"]] = {"status": state, "last_activity": d, "days_since": days}
    return out


def working_days(start: date, end: date, weekdays: list[int]) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() in weekdays:
            out.append(d)
        d += timedelta(days=1)
    return out
