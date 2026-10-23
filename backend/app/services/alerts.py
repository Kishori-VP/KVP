"""Live Stakeholder alerts (PRD 4.10 / 4.15)."""

from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.core.permissions import Role
from app.db import collections as c
from app.services import activity
from app.services.app_settings import get_setting
from app.services.beneficiaries import OPEN_CASE_STATUSES
from app.services.lookups import MANDATORY_CONTACT_CATEGORIES
from app.services.targets import with_progress
from app.utils.dates import day_range, to_date, to_dt, today_local, utcnow
from app.utils.mongo import serialize


def _villages_label(u: dict, names: dict) -> str | None:
    ids = u.get("village_ids") or ([u["village_id"]] if u.get("village_id") else [])
    return ", ".join(n for n in (names.get(i) for i in ids) if n) or None


async def compute_alerts(db: AsyncDatabase, village_ids: list | None = None) -> dict:
    today = today_local()
    now = utcnow()
    vscope = {"village_id": {"$in": village_ids}} if village_ids is not None else {}
    villages = {v["_id"]: v["name"] async for v in db[c.VILLAGES].find({}, {"name": 1})}
    users = {u["_id"]: u["name"] async for u in db[c.USERS].find({}, {"name": 1})}

    # --- overdue reports
    rules = await get_setting(db, "reporting")
    overdue_reports = []
    if rules["expected_activity_report"] == "daily":
        check_until = today - timedelta(days=rules["grace_days"])
        days = activity.working_days(check_until - timedelta(days=6), check_until, rules["working_days"])
        s, e = day_range(check_until - timedelta(days=6), check_until)
        vq = {"role": Role.VOLUNTEER.value, "is_active": True, "village_id": {"$ne": None}}
        if village_ids is not None:
            vq["village_ids"] = {"$in": village_ids}
        async for v in db[c.USERS].find(vq):
            first = await db[c.VOLUNTEER_ASSIGNMENTS].find_one({"volunteer_id": v["_id"]}, sort=[("start_date", 1)])
            active_from = to_date(first["start_date"]) if first else to_date(v["created_at"])
            due = [d for d in days if d >= active_from]
            got = {r["report_date"].date() async for r in db[c.ACTIVITY_REPORTS].find(
                {"volunteer_id": v["_id"], "report_date": {"$gte": s, "$lt": e}}, {"report_date": 1})}
            missing = [d for d in due if d not in got]
            if missing:
                overdue_reports.append({"type": "missing_daily_reports", "volunteer_id": v["_id"], "volunteer": v["name"],
                                        "village": _villages_label(v, villages), "missing_dates": missing,
                                        "count": len(missing)})
    async for ev in db[c.EVENTS].find({"status": "scheduled", "end_at": {"$lt": now}, **vscope}, {"attendance": 0}):
        overdue_reports.append({"type": "event_report_overdue", "event_id": ev["_id"], "title": ev["title"],
                                "village": villages.get(ev["village_id"]),
                                "volunteer": users.get(ev.get("responsible_volunteer_id")),
                                "days_overdue": (now - ev["end_at"]).days})

    # --- unresolved cases
    esc = await get_setting(db, "escalation_rules")
    unresolved = []
    stale_before = now - timedelta(days=esc["case_no_update_days"])
    async for cs in db[c.CASES].find({"status": {"$in": OPEN_CASE_STATUSES}, **vscope,
                                      "$or": [{"due_date": {"$lt": to_dt(today)}}, {"last_activity_at": {"$lt": stale_before}}]},
                                     {"timeline": 0}):
        overdue_days = (today - to_date(cs["due_date"])).days if cs.get("due_date") and to_date(cs["due_date"]) < today else 0
        unresolved.append({
            "case_id": cs["_id"], "case_code": cs["case_code"], "girl_code": cs.get("girl_code"),
            "category": cs["category"], "severity": cs["severity"], "status": cs["status"],
            "village": villages.get(cs["village_id"]), "assigned_to": users.get(cs.get("assigned_to")),
            "overdue_days": overdue_days,
            "days_since_update": (now - cs["last_activity_at"]).days,
            "needs_escalation": overdue_days >= esc["escalate_after_overdue_days"] and cs["status"] != "escalated",
        })
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unresolved.sort(key=lambda x: (sev_rank[x["severity"]], -x["overdue_days"]))

    # --- inactive villages
    statuses = await activity.village_activity_status(db)
    inactive = [{"village_id": vid, "village": villages.get(vid), **st} for vid, st in statuses.items()
                if st["status"] != "on_track" and (village_ids is None or vid in village_ids)]
    inactive.sort(key=lambda x: -(x["days_since"] if x["days_since"] is not None else 10_000))

    # --- missed / at-risk targets
    tscope = {"$or": [{"village_id": {"$in": village_ids}}, {"village_ids": {"$in": village_ids}}]} if village_ids is not None else {}
    recent = await db[c.TARGETS].find({"status": "active", **tscope,
                                       "period_end": {"$gte": to_dt(today - timedelta(days=30))},
                                       "period_start": {"$lte": to_dt(today)}}).to_list()
    enriched = await with_progress(db, recent)
    missed = [{"target_id": t["_id"], "title": t["title"], "volunteer": users.get(t["volunteer_id"]),
               "village": villages.get(t["village_id"]) or _villages_label(t, villages), "target_value": t["target_value"],
               **t["progress"]}
              for t in enriched if t["progress"]["status"] in ("missed", "at_risk")]
    missed.sort(key=lambda x: (x["status"] != "missed", x["progress_pct"]))

    # --- villages without full mandatory contacts
    contact_gaps = []
    async for v in db[c.VILLAGES].find({"status": "active", **({"_id": {"$in": village_ids}} if village_ids is not None else {})}):
        have = {ct["category"] async for ct in db[c.CONTACTS].find(
            {"village_id": v["_id"], "is_active": True, "category": {"$in": MANDATORY_CONTACT_CATEGORIES}}, {"category": 1})}
        missing = [m for m in MANDATORY_CONTACT_CATEGORIES if m not in have]
        if missing:
            contact_gaps.append({"village_id": v["_id"], "village": v["name"], "missing": missing})

    result = {
        "overdue_reports": overdue_reports,
        "unresolved_cases": unresolved,
        "inactive_villages": inactive,
        "missed_targets": missed,
        "missing_village_contacts": contact_gaps,
    }
    result["counts"] = {k: len(v) for k, v in result.items()}
    return serialize(result)
