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
