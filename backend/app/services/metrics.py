"""Activity metrics per volunteer/village/date range.

Used for target progress, volunteer performance and dashboards. Each metric
counts approved-or-pending records (rejected records never count).

Daily activity reports (the digitised Google Form) and structured records
(home visits, events) can describe the same work. To avoid double counting,
report-based counts are only used for days with no structured record of that kind.
"""

from datetime import date

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.services.events import local_day_bounds
from app.utils.dates import day_range

NOT_REJECTED = {"approval.status": {"$ne": "rejected"}}


def _scope(volunteer_id: ObjectId | None, village_id, vol_field: str = "volunteer_id") -> dict:
    q: dict = {}
    if volunteer_id:
        q[vol_field] = volunteer_id
    if village_id:
        if isinstance(village_id, (list, tuple, set)):
            v_list = list(village_id)
            if len(v_list) == 1:
                q["village_id"] = v_list[0]
            elif len(v_list) > 1:
                q["village_id"] = {"$in": v_list}
        else:
            q["village_id"] = village_id
    return q


async def meeting_event_types(db: AsyncDatabase) -> list[str]:
    return [d["code"] async for d in db[c.LOOKUPS].find({"type": "event_type", "attributes.is_meeting": True})]


async def home_visits(db, volunteer_id, village_id, start: date, end: date) -> int:
    s, e = day_range(start, end)
    q = {**_scope(volunteer_id, village_id), "status": "completed", "visit_date": {"$gte": s, "$lt": e}, **NOT_REJECTED}
    visits = await db[c.HOME_VISITS].find(q, {"visit_date": 1, "volunteer_id": 1}).to_list()
    covered = {(v["volunteer_id"], v["visit_date"].date()) for v in visits}
    rq = {**_scope(volunteer_id, village_id), "report_date": {"$gte": s, "$lt": e}, **NOT_REJECTED}
    from_reports = 0
    async for r in db[c.ACTIVITY_REPORTS].find(rq, {"report_date": 1, "volunteer_id": 1, "home_visits_count": 1}):
        if (r["volunteer_id"], r["report_date"].date()) not in covered:
            from_reports += r.get("home_visits_count") or 0
    return len(visits) + from_reports


async def events_completed(db, volunteer_id, village_id, start, end, event_types: list[str] | None = None) -> list[dict]:
    s, e = local_day_bounds(start, end)
    q = {**_scope(volunteer_id, village_id, "responsible_volunteer_id"), "status": "completed",
         "start_at": {"$gte": s, "$lt": e}, **NOT_REJECTED}
    if event_types is not None:
        q["event_type"] = {"$in": event_types}
    return await db[c.EVENTS].find(q, {"start_at": 1, "responsible_volunteer_id": 1, "attendance": 1,
                                       "event_type": 1, "village_id": 1, "other_participants": 1}).to_list()


async def group_meetings(db, volunteer_id, village_id, start, end) -> int:
    meetings = await events_completed(db, volunteer_id, village_id, start, end, await meeting_event_types(db))
    covered = {(m.get("responsible_volunteer_id"), m["start_at"].date()) for m in meetings}
    s, e = day_range(start, end)
    rq = {**_scope(volunteer_id, village_id), "report_date": {"$gte": s, "$lt": e}, **NOT_REJECTED}
    from_reports = 0
    async for r in db[c.ACTIVITY_REPORTS].find(rq, {"report_date": 1, "volunteer_id": 1, "group_ids": 1}):
        if (r["volunteer_id"], r["report_date"].date()) not in covered:
            from_reports += len(r.get("group_ids") or [])
    return len(meetings) + from_reports


async def girls_covered_ids(db, volunteer_id, village_id, start, end) -> set:
    s, e = day_range(start, end)
    ids: set = set()
    async for v in db[c.HOME_VISITS].find({**_scope(volunteer_id, village_id), "status": "completed",
                                           "visit_date": {"$gte": s, "$lt": e}, **NOT_REJECTED}, {"girl_ids": 1}):
        ids.update(v.get("girl_ids") or [])
    async for r in db[c.ACTIVITY_REPORTS].find({**_scope(volunteer_id, village_id), "report_date": {"$gte": s, "$lt": e},
                                                **NOT_REJECTED}, {"home_visit_girl_ids": 1}):
        ids.update(r.get("home_visit_girl_ids") or [])
    for ev in await events_completed(db, volunteer_id, village_id, start, end):
        ids.update(a["girl_id"] for a in ev.get("attendance", []) if a.get("present"))
    return ids


async def follow_ups(db, volunteer_id, village_id, start, end) -> int:
    s, e = day_range(start, end)
    visits = await db[c.HOME_VISITS].count_documents({
        **_scope(volunteer_id, village_id), "status": "completed", "purpose": {"$in": ["follow_up", "case_follow_up"]},
        "visit_date": {"$gte": s, "$lt": e}, **NOT_REJECTED})
    match: dict = {"timeline.type": "follow_up"}
    if village_id:
        match["village_id"] = village_id
    elem: dict = {"type": "follow_up", "at": {"$gte": s, "$lt": e}}
    if volunteer_id:
        elem["by"] = volunteer_id
    pipeline = [{"$match": match}, {"$unwind": "$timeline"},
                {"$match": {f"timeline.{k}": v for k, v in elem.items()}}, {"$count": "n"}]
    notes = [d async for d in await db[c.CASES].aggregate(pipeline)]
    return visits + (notes[0]["n"] if notes else 0)


async def case_closures(db, volunteer_id, village_id, start, end) -> int:
    s, e = day_range(start, end)
    q = {**_scope(volunteer_id, village_id, "assigned_to"), "status": {"$in": ["resolved", "closed"]},
         "resolved_at": {"$gte": s, "$lt": e}}
    return await db[c.CASES].count_documents(q)


async def health_screenings(db, volunteer_id, village_id, start, end) -> int:
    s, e = day_range(start, end)
    return await db[c.HEALTH_RECORDS].count_documents(
        {**_scope(volunteer_id, village_id, "recorded_by"), "recorded_on": {"$gte": s, "$lt": e}})


async def activity_reports(db, volunteer_id, village_id, start, end) -> int:
    s, e = day_range(start, end)
    return await db[c.ACTIVITY_REPORTS].count_documents(
        {**_scope(volunteer_id, village_id), "report_date": {"$gte": s, "$lt": e}, **NOT_REJECTED})


async def compute(db: AsyncDatabase, metric: str, volunteer_id, village_id, start: date, end: date) -> int:
    if metric == "home_visits":
        return await home_visits(db, volunteer_id, village_id, start, end)
    if metric == "group_meetings":
        return await group_meetings(db, volunteer_id, village_id, start, end)
    if metric == "events":
        return len(await events_completed(db, volunteer_id, village_id, start, end))
    if metric == "girls_covered":
        return len(await girls_covered_ids(db, volunteer_id, village_id, start, end))
    if metric == "follow_ups":
        return await follow_ups(db, volunteer_id, village_id, start, end)
    if metric == "case_closures":
        return await case_closures(db, volunteer_id, village_id, start, end)
    if metric == "health_screenings":
        return await health_screenings(db, volunteer_id, village_id, start, end)
    if metric == "activity_reports":
        return await activity_reports(db, volunteer_id, village_id, start, end)
    raise ValueError(f"Unknown metric {metric}")


async def activity_summary(db: AsyncDatabase, volunteer_id, village_id, start: date, end: date) -> dict:
    """All headline metrics for one volunteer and/or village."""
    events = await events_completed(db, volunteer_id, village_id, start, end)
    return {
        "home_visits": await home_visits(db, volunteer_id, village_id, start, end),
        "group_meetings": await group_meetings(db, volunteer_id, village_id, start, end),
        "events": len(events),
        "event_attendance": sum(sum(1 for a in ev.get("attendance", []) if a.get("present")) for ev in events),
        "girls_covered": len(await girls_covered_ids(db, volunteer_id, village_id, start, end)),
        "follow_ups": await follow_ups(db, volunteer_id, village_id, start, end),
        "case_closures": await case_closures(db, volunteer_id, village_id, start, end),
        "health_screenings": await health_screenings(db, volunteer_id, village_id, start, end),
        "activity_reports": await activity_reports(db, volunteer_id, village_id, start, end),
    }
