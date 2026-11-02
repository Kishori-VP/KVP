import re
from datetime import UTC, date, datetime, time, timedelta

from app.db import collections as c
from app.services.app_settings import get_setting
from app.services.messaging import normalize_phone, send_sms
from app.utils.dates import local_tz, today_local, utcnow

DEFAULT_DURATION = timedelta(hours=2)
DEFAULT_PRE_CHECKLIST = [
    "Venue confirmed",
    "Participants informed",
    "Materials / kits ready",
    "Attendance register ready",
    "Resource person confirmed",
]
DEFAULT_POST_CHECKLIST = [
    "Attendance captured",
    "Photos uploaded",
    "Post-event report submitted",
    "Follow-up actions assigned",
    "Expenditure recorded",
]


def local_to_utc(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=local_tz()).astimezone(UTC)


def event_window(d: date, start: str, end: str | None) -> tuple[datetime, datetime]:
    start_at = local_to_utc(d, start)
    end_at = local_to_utc(d, end) if end else start_at + DEFAULT_DURATION
    return start_at, end_at


def display_status(ev: dict) -> str:
    """upcoming | today | overdue | completed | cancelled"""
    if ev["status"] in ("completed", "cancelled"):
        return ev["status"]
    now = utcnow()
    if ev["end_at"] < now:
        return "overdue"
    if ev["start_at"].astimezone(local_tz()).date() == today_local():
        return "today"
    return "upcoming"


def status_query(display: str) -> dict:
    now = utcnow()
    today_start = datetime.combine(today_local(), time.min, tzinfo=local_tz()).astimezone(UTC)
    tomorrow_start = today_start + timedelta(days=1)
    return {
        "completed": {"status": "completed"},
        "cancelled": {"status": "cancelled"},
        "overdue": {"status": "scheduled", "end_at": {"$lt": now}},
        "upcoming": {"status": "scheduled", "end_at": {"$gte": now}},
        "today": {"status": {"$ne": "cancelled"}, "start_at": {"$gte": today_start, "$lt": tomorrow_start}},
    }[display]


def local_day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    s = datetime.combine(start, time.min, tzinfo=local_tz()).astimezone(UTC)
    e = datetime.combine(end + timedelta(days=1), time.min, tzinfo=local_tz()).astimezone(UTC)
    return s, e


def summarize_attendance(ev: dict) -> dict:
    att = ev.get("attendance") or []
    present = sum(1 for a in att if a.get("present"))
    others = sum((ev.get("other_participants") or {}).values())
    expected = ev.get("expected_participants") or 0
    return {
        "girls_present": present,
        "girls_absent": len(att) - present,
        "other_participants": others,
        "total_present": present + others,
        "expected": expected,
        "attendance_vs_expected": round((present + others) / expected, 2) if expected else None,
    }


async def remind_participants(db, ev: dict, actor: dict | None = None) -> dict:
    """SMS the families of girls in the event's invited groups (one message per phone number)."""
    cfg = await get_setting(db, "messaging")
    village = await db[c.VILLAGES].find_one({"_id": ev["village_id"]}, {"name": 1, "name_mr": 1})
    local = ev["start_at"].astimezone(local_tz())
    body = cfg["participant_reminder_template"].format(
        title=ev["title"], date=local.strftime("%d-%m-%Y"), time=local.strftime("%H:%M"),
        place=ev.get("location_name") or (village or {}).get("name_mr") or (village or {}).get("name") or "")
    counts = {"sent": 0, "logged": 0, "failed": 0, "skipped": 0, "duplicate": 0, "no_phone": 0}
    seen = set()
    async for g in db[c.GIRLS].find({"group_id": {"$in": ev.get("group_ids", [])}, "is_deleted": {"$ne": True},
                                     "enrollment.status": "active"},
                                    {"girl_code": 1, "name": 1, "phone": 1, "household.phone": 1}):
        phone = normalize_phone(g.get("phone")) or normalize_phone((g.get("household") or {}).get("phone"))
        if not phone:
            counts["no_phone"] += 1
            continue
        if phone in seen:
            continue
        seen.add(phone)
        doc = await send_sms(db, phone, body, purpose="event_participant_reminder", entity_type="event",
                             entity_id=ev["_id"], recipient_name=g.get("name") or g["girl_code"],
                             dedupe_key=f"event_reminder:{ev['_id']}:{phone}",
                             created_by=actor["_id"] if actor else None)
        counts["duplicate" if doc is None else doc["status"]] += 1
    return counts


async def auto_schedule_monthly_meetings(db, year: int, month: int) -> dict:
    """Automatically create recurring monthly meeting events at the beginning of the month for all Balpanchayat and Kishori groups."""
    start_of_month = datetime(year, month, 1, 0, 0, 0, tzinfo=local_tz())
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=local_tz())
    else:
        end_of_month = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=local_tz())
    s_utc = start_of_month.astimezone(UTC)
    e_utc = end_of_month.astimezone(UTC)

    groups = await db[c.GROUPS].find({
        "group_type": {"$in": ["kishori", "bal_panchayat"]},
        "is_active": True,
        "is_deleted": {"$ne": True},
    }).to_list()

    volunteers = await db[c.USERS].find({"role": "volunteer", "is_active": True}).to_list()
    vol_by_group = {}
    vol_by_village = {}
    for v in volunteers:
        for gid in v.get("group_ids", []):
            vol_by_group[gid] = v["_id"]
        for vid in v.get("village_ids", []):
            vol_by_village[vid] = v["_id"]

    created_events = 0
    now = utcnow()

    for g in groups:
        gtype = g.get("group_type")
        event_type = "kishori_meeting" if gtype == "kishori" else "bal_panchayat_meeting"

        exists = await db[c.EVENTS].find_one({
            "group_ids": g["_id"],
            "event_type": event_type,
            "start_at": {"$gte": s_utc, "$lt": e_utc},
            "is_deleted": {"$ne": True},
        })
        if exists:
            continue

        meeting_date = date(year, month, 1)
        sched = g.get("meeting_schedule") or {}
        time_str = sched.get("time") or "10:00"
        start_at, end_at = event_window(meeting_date, time_str, None)

        vol_id = g.get("responsible_volunteer_id") or vol_by_group.get(g["_id"]) or vol_by_village.get(g["village_id"])

        if gtype == "kishori":
            title = f"{g['name']} - किशोरी गट मासिक बैठक"
        else:
            title = f"{g['name']} - बालपंचायत मासिक बैठक"

        doc = {
            "title": title,
            "event_type": event_type,
            "objective": f"{g['name']} monthly meeting for {year}-{month:02d}",
            "village_id": g["village_id"],
            "taluka_id": g.get("taluka_id"),
            "location_name": "गाव / अंगणवाडी",
            "location": None,
            "start_at": start_at,
            "end_at": end_at,
            "start_time": time_str,
            "end_time": "12:00",
            "responsible_volunteer_id": vol_id,
            "expected_participants": len(g.get("members", [])) if gtype == "bal_panchayat" else 15,
            "group_ids": [g["_id"]],
            "status": "scheduled",
            "is_historical": False,
            "planned": True,
            "is_auto_scheduled": True,
            "recurrence": {
                "frequency": "monthly",
                "period": f"{year:04d}-{month:02d}",
            },
            "pre_checklist": [{"item": item, "done": False, "notes": None, "done_at": None, "done_by": None}
                              for item in DEFAULT_PRE_CHECKLIST],
            "post_checklist": [{"item": item, "done": False, "notes": None, "done_at": None, "done_by": None}
                               for item in DEFAULT_POST_CHECKLIST],
            "attendance": [],
            "other_participants": {},
            "report": None,
            "expenditure": {"items": [], "total": 0, "resources_used": []},
            "planned_budget": None,
            "notify_participants": False,
            "media_ids": [],
            "reschedule_history": [],
            "cancel_reason": None,
            "approval": {"status": "not_required", "by": None, "at": None, "remarks": None},
            "created_by": None,
            "created_at": now,
            "updated_at": now,
        }

        await db[c.EVENTS].insert_one(doc)
        created_events += 1

    return {
        "created": created_events,
        "year": year,
        "month": month,
        "total_groups": len(groups),
    }
