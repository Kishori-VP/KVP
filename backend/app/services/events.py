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


# A group-tracked meeting (one village meeting covering several groups) is not overdue once its
# time passes: it stays "ongoing" until every group's meeting is marked done, which completes it.
NOT_ONGOING = {"track_groups": {"$ne": True}}


def groups_pending(ev: dict) -> list:
    """Group ids of a group-tracked meeting whose meeting is not marked done yet."""
    done = {g["group_id"] for g in ev.get("groups_done") or []}
    return [gid for gid in ev.get("group_ids") or [] if gid not in done]


def display_status(ev: dict) -> str:
    """upcoming | today | ongoing | overdue | completed | cancelled"""
    if ev["status"] in ("completed", "cancelled"):
        return ev["status"]
    now = utcnow()
    if ev["end_at"] < now:
        return "ongoing" if ev.get("track_groups") else "overdue"
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
        "overdue": {"status": "scheduled", "end_at": {"$lt": now}, **NOT_ONGOING},
        "ongoing": {"status": "scheduled", "end_at": {"$lt": now}, "track_groups": True},
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


MEETING_EVENT_TYPES = {"kishori": "kishori_meeting", "bal_panchayat": "bal_panchayat_meeting"}


def month_bounds_utc(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=local_tz())
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=local_tz())
    return start.astimezone(UTC), end.astimezone(UTC)


def suggested_meeting_date(schedule: dict | None, year: int, month: int) -> date | None:
    """The group's usual meeting day in that month (e.g. "2nd Tuesday"), if its schedule says so."""
    schedule = schedule or {}
    dow = schedule.get("day_of_week")
    if dow is None:
        return None
    first = date(year, month, 1)
    first_match = first + timedelta(days=(dow - first.weekday()) % 7)
    candidate = first_match + timedelta(weeks=(schedule.get("week_of_month") or 1) - 1)
    while candidate.month != month:  # "5th Friday" in a month that has only four
        candidate -= timedelta(weeks=1)
    return candidate


async def monthly_planner_rows(db, year: int, month: int) -> list[dict]:
    """Every active Kishori / Bal Panchayat group with its suggested slot and any meeting already set."""
    s_utc, e_utc = month_bounds_utc(year, month)
    groups = await db[c.GROUPS].find({
        "group_type": {"$in": list(MEETING_EVENT_TYPES)}, "is_active": True, "is_deleted": {"$ne": True},
    }).to_list()
    village_ids = {g.get("village_id") for g in groups}
    villages = {v["_id"]: v for v in await db[c.VILLAGES].find({"_id": {"$in": list(village_ids)}},
                                                                {"name": 1, "name_mr": 1}).to_list()}
    volunteers = await db[c.USERS].find({"role": "volunteer", "is_active": True},
                                        {"name": 1, "group_ids": 1, "village_ids": 1}).to_list()
    vol_names = {v["_id"]: v.get("name") for v in volunteers}
    vol_by_group, vol_by_village = {}, {}
    for v in volunteers:
        for gid in v.get("group_ids", []):
            vol_by_group[gid] = v["_id"]
        for vid in v.get("village_ids", []):
            vol_by_village[vid] = v["_id"]
    existing = {}
    async for ev in db[c.EVENTS].find({
        "group_ids": {"$in": [g["_id"] for g in groups]},
        "event_type": {"$in": list(MEETING_EVENT_TYPES.values())},
        "start_at": {"$gte": s_utc, "$lt": e_utc}, "is_deleted": {"$ne": True},
    }, {"group_ids": 1, "start_at": 1, "event_type": 1}).sort("start_at", 1):
        for gid in ev.get("group_ids", []):
            existing.setdefault((gid, ev["event_type"]), ev)

    rows = []
    for g in groups:
        etype = MEETING_EVENT_TYPES[g["group_type"]]
        vol_id = g.get("responsible_volunteer_id") or vol_by_group.get(g["_id"]) or vol_by_village.get(g.get("village_id"))
        village = villages.get(g.get("village_id")) or {}
        ev = existing.get((g["_id"], etype))
        suggested = suggested_meeting_date(g.get("meeting_schedule"), year, month)
        rows.append({
            "group_id": str(g["_id"]),
            "group_name": g.get("name"),
            "group_type": g["group_type"],
            "event_type": etype,
            "village_id": str(g["village_id"]) if g.get("village_id") else None,
            "village_name": village.get("name"),
            "village_name_mr": village.get("name_mr"),
            "suggested_date": suggested.isoformat() if suggested else None,
            "suggested_time": (g.get("meeting_schedule") or {}).get("time") or "10:00",
            "responsible_volunteer_id": str(vol_id) if vol_id else None,
            "responsible_volunteer_name": vol_names.get(vol_id),
            "existing_event_id": str(ev["_id"]) if ev else None,
            "existing_start_at": ev["start_at"].isoformat() if ev else None,
        })
    rows.sort(key=lambda r: (r["village_name"] or "", r["group_type"], r["group_name"] or ""))
    return rows


def meeting_event_doc(group: dict, meeting_date: date, start_time: str, end_time: str | None,
                      volunteer_id, actor_id, year: int, month: int) -> dict:
    """A planned Kishori / Bal Panchayat monthly meeting for one group."""
    gtype = group["group_type"]
    start_at, end_at = event_window(meeting_date, start_time, end_time)
    label = "किशोरी गट मासिक बैठक" if gtype == "kishori" else "बालपंचायत मासिक बैठक"
    now = utcnow()
    return {
        "title": f"{group['name']} - {label}",
        "event_type": MEETING_EVENT_TYPES[gtype],
        "objective": f"{group['name']} monthly meeting for {year}-{month:02d}",
        "village_id": group["village_id"],
        "taluka_id": group.get("taluka_id"),
        "location_name": "गाव / अंगणवाडी",
        "location": None,
        "start_at": start_at,
        "end_at": end_at,
        "start_time": start_time,
        "end_time": end_time or end_at.astimezone(local_tz()).strftime("%H:%M"),
        "responsible_volunteer_id": volunteer_id,
        "expected_participants": len(group.get("members", [])) if gtype == "bal_panchayat" else 15,
        "group_ids": [group["_id"]],
        "status": "scheduled",
        "is_historical": False,
        "planned": True,
        "is_auto_scheduled": False,
        "source": "monthly_planner",
        "recurrence": {"frequency": "monthly", "period": f"{year:04d}-{month:02d}"},
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
        "created_by": actor_id,
        "created_at": now,
        "updated_at": now,
    }
