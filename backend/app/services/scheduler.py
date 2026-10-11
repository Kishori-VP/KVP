"""Background jobs: reminders, Stakeholder alerts, case escalation and scheduled reports.

Every notification uses a dedupe key, so running the jobs repeatedly (every 15
minutes by default) never sends the same reminder twice.
"""

import asyncio
import logging
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.db import collections as c
from app.services import notifications as notif
from app.services.alerts import compute_alerts
from app.services.app_settings import get_setting
from app.services.beneficiaries import OPEN_CASE_STATUSES, refresh_case_summary
from app.services.events import local_day_bounds, remind_participants
from app.services.report_delivery import run_due_schedules
from app.services.targets import with_progress
from app.utils.dates import to_dt, today_local, utcnow

log = logging.getLogger("kvp.scheduler")


async def _stakeholder_alerts(db: AsyncDatabase) -> int:
    alerts = await compute_alerts(db)
    today = today_local().isoformat()
    week = today_local().strftime("%G-W%V")
    n = 0
    for a in alerts["missed_targets"]:
        if a["status"] == "missed":
            n += await notif.notify_stakeholders(
                db, "target_missed", f"Target missed: {a['title']}",
                f"{a['volunteer']} ({a['village']}): {a['achieved']}/{a['target_value']}",
                entity_type="target", severity="high", dedupe_key=f"target_missed:{a['target_id']}")
    for a in alerts["overdue_reports"]:
        if a["type"] == "event_report_overdue":
            n += await notif.notify_stakeholders(
                db, "event_report_overdue", f"Event report overdue: {a['title']}",
                f"{a['village']} · {a['volunteer'] or 'no volunteer'} · {a['days_overdue']} day(s) overdue",
                entity_type="event", severity="medium", dedupe_key=f"event_overdue:{a['event_id']}:{today}")
        else:
            n += await notif.notify_stakeholders(
                db, "reports_missing", f"Daily reports missing: {a['volunteer']}",
                f"{a['count']} missing in the last week ({a['village']})",
                entity_type="user", severity="medium", dedupe_key=f"reports_missing:{a['volunteer_id']}:{week}")
    for a in alerts["inactive_villages"]:
        if a["status"] == "no_recent_activity":
            since = f"{a['days_since']} days" if a["days_since"] is not None else "ever"
            n += await notif.notify_stakeholders(
                db, "village_inactive", f"No recent activity: {a['village']}", f"Last field activity: {since}",
                entity_type="village", severity="medium", dedupe_key=f"village_inactive:{a['village_id']}:{week}")
    return n


async def _case_escalations(db: AsyncDatabase) -> int:
    rules = await get_setting(db, "escalation_rules")
    today = today_local()
    n = 0
    async for cs in db[c.CASES].find({"status": {"$in": OPEN_CASE_STATUSES}, "due_date": {"$lt": to_dt(today)}}, {"timeline": 0}):
        overdue = (today - cs["due_date"].date()).days
        key = f"case_overdue:{cs['_id']}:{today.isoformat()}"
        if cs.get("assigned_to"):
            n += await notif.notify(db, cs["assigned_to"], "case_overdue", f"Case {cs['case_code']} is overdue",
                                    cs.get("next_action") or cs["title"], entity_type="case", entity_id=cs["_id"],
                                    severity=cs["severity"], dedupe_key=key)
        if overdue >= rules["escalate_after_overdue_days"] and cs["status"] != "escalated":
            n += await notif.notify_stakeholders(
                db, "case_escalation_reminder", f"Escalate? {cs['case_code']} ({cs['severity']})",
                f"{overdue} days overdue: {cs['title']}", entity_type="case", entity_id=cs["_id"],
                severity=cs["severity"], dedupe_key=key)
            if rules["auto_escalate"]:
                await db[c.CASES].update_one({"_id": cs["_id"]}, {
                    "$set": {"status": "escalated", "last_activity_at": utcnow()},
                    "$push": {"timeline": {"at": utcnow(), "by": None, "by_name": "system", "type": "status_change",
                                           "text": f"Auto-escalated: {overdue} days overdue",
                                           "from": cs["status"], "to": "escalated"}}})
                await refresh_case_summary(db, cs["girl_id"])
    return n


async def _volunteer_reminders(db: AsyncDatabase) -> int:
    today = today_local()
    tomorrow = today + timedelta(days=1)
    n = 0
    s, e = local_day_bounds(today, tomorrow)
    async for ev in db[c.EVENTS].find({"status": "scheduled", "start_at": {"$gte": s, "$lt": e},
                                       "responsible_volunteer_id": {"$ne": None}}, {"attendance": 0}):
        pending = [i["item"] for i in ev.get("pre_checklist", []) if not i["done"]]
        msg = f"Starts {ev['start_time']}" + (f". Pending checklist: {', '.join(pending[:3])}" if pending else "")
        n += await notif.notify(db, ev["responsible_volunteer_id"], "event_reminder", f"Upcoming event: {ev['title']}",
                                msg, entity_type="event", entity_id=ev["_id"], dedupe_key=f"event_reminder:{ev['_id']}")
    if (await get_setting(db, "messaging"))["participant_reminders_enabled"]:
        ts, te = local_day_bounds(tomorrow, tomorrow)
        async for ev in db[c.EVENTS].find({"status": "scheduled", "notify_participants": True,
                                           "start_at": {"$gte": ts, "$lt": te}}, {"attendance": 0}):
            res = await remind_participants(db, ev)
            n += res["sent"] + res["logged"]
    async for hv in db[c.HOME_VISITS].find({"status": "planned", "visit_date": {"$gte": to_dt(today), "$lte": to_dt(tomorrow)}}):
        n += await notif.notify(db, hv["volunteer_id"], "visit_reminder", "Planned home visit",
                                f"Scheduled for {hv['visit_date']:%d %b}", entity_type="home_visit", entity_id=hv["_id"],
                                dedupe_key=f"visit_reminder:{hv['_id']}")
    async for cs in db[c.CASES].find({"status": {"$in": OPEN_CASE_STATUSES}, "assigned_to": {"$ne": None},
                                      "due_date": {"$gte": to_dt(today), "$lte": to_dt(tomorrow)}}, {"timeline": 0}):
        n += await notif.notify(db, cs["assigned_to"], "case_follow_up_due", f"Follow-up due: {cs['case_code']}",
                                cs.get("next_action") or cs["title"], entity_type="case", entity_id=cs["_id"],
                                severity=cs["severity"], dedupe_key=f"case_due:{cs['_id']}:{cs['due_date']:%Y%m%d}")
    # Targets: starting today, deadline approaching, low performance.
    thresholds = await get_setting(db, "target_thresholds")
    running = await db[c.TARGETS].find({"status": "active", "period_start": {"$lte": to_dt(today)},
                                        "period_end": {"$gte": to_dt(today)}}).to_list()
    for t in await with_progress(db, running, thresholds):
        p = t["progress"]
        if t["period_start"].date() == today:
            n += await notif.notify(db, t["volunteer_id"], "target_period_started", f"Target period started: {t['title']}",
                                    f"Target {t['target_value']} by {t['period_end']:%d %b}", entity_type="target",
                                    entity_id=t["_id"], dedupe_key=f"target_start:{t['_id']}")
        if p["deadline_approaching"]:
            n += await notif.notify(db, t["volunteer_id"], "target_deadline", f"Deadline near: {t['title']}",
                                    f"{p['achieved']}/{t['target_value']} done, {p['days_left']} day(s) left",
                                    entity_type="target", entity_id=t["_id"], severity="medium",
                                    dedupe_key=f"target_deadline:{t['_id']}:{today.isoformat()}")
        if p["low_performance"]:
            n += await notif.notify(db, t["volunteer_id"], "target_low_performance", f"Behind on: {t['title']}",
                                    f"{p['progress_pct']}% done vs {p['elapsed_pct']}% of the period elapsed",
                                    entity_type="target", entity_id=t["_id"], severity="medium",
                                    dedupe_key=f"target_low:{t['_id']}:{today.strftime('%G-W%V')}")
    return n


async def run_jobs_once(db: AsyncDatabase) -> dict:
    return {
        "stakeholder_alerts": await _stakeholder_alerts(db),
        "case_escalations": await _case_escalations(db),
        "volunteer_reminders": await _volunteer_reminders(db),
        "scheduled_reports_run": await run_due_schedules(db),
    }


async def scheduler_loop(get_db) -> None:
    await asyncio.sleep(10)  # let the app finish starting
    while True:
        try:
            result = await run_jobs_once(get_db())
            log.info("Scheduler run: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler run failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)
