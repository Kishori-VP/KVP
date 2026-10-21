"""Stakeholder-configurable settings, stored in the app_settings collection.

Each setting is a document {key, value, updated_at, updated_by}. Stored values
are merged over the defaults below so new options get sensible values without
a migration.
"""

import copy
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.permissions import DEFAULT_VOLUNTEER_PERMISSIONS
from app.db import collections as c
from app.utils.dates import utcnow

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "target_thresholds": {
        # Achieved / expected-by-now ratio at or above which a target is On Track.
        "on_track_min_ratio": 0.9,
        # Below this ratio a target is flagged as low performance in notifications.
        "low_performance_ratio": 0.5,
        # Notify when this many days (or fewer) remain and the target is not achieved.
        "deadline_warning_days": 2,
    },
    "escalation_rules": {
        # Default due date (days after opening) per severity when none is given.
        "case_due_days_by_severity": {"critical": 2, "high": 7, "medium": 14, "low": 30},
        # A case with no timeline activity for this many days is "stale".
        "case_no_update_days": 7,
        # Overdue cases are flagged for escalation after this many days past due.
        "escalate_after_overdue_days": 3,
        "auto_escalate": False,
    },
    "village_status": {
        # Last field activity within N days -> On Track; within M days -> Delayed;
        # older -> No Recent Activity.
        "on_track_within_days": 7,
        "delayed_within_days": 21,
    },
    "duplicate_matching": {
        "fields": ["name", "village_id", "age", "household.father_name"],
        "name_similarity_threshold": 0.85,
        "age_tolerance_years": 1,
        "min_score": 0.75,
    },
    "girl_id": {"prefix": "KVP-2627-", "pad": 0},
    "anaemia_thresholds": {
        # Haemoglobin (g/dL) cut-offs for adolescent girls (WHO).
        "severe_below": 8.0,
        "moderate_below": 11.0,
        "mild_below": 12.0,
    },
    "reporting": {
        # Each Volunteer is expected to submit one daily activity report on working days.
        "expected_activity_report": "daily",
        "working_days": [0, 1, 2, 3, 4, 5],  # Monday=0 ... Saturday=5
        "grace_days": 1,
    },
    "validation_rules": {
        "girl": {"required": ["village_id"], "rules": {"age": {"min": 8, "max": 21}}},
        "home_visit": {"required": ["volunteer_id", "village_id", "visit_date"], "rules": {}},
        "event": {"required": ["title", "event_type", "village_id", "start_at"], "rules": {}},
        "contact": {"required": ["name", "mobile"], "rules": {"mobile": {"pattern": r"^[6-9]\d{9}$"}}},
    },
    "permissions": {"volunteer": DEFAULT_VOLUNTEER_PERMISSIONS},
    "messaging": {
        # SMS reminders to invited girls/families for events flagged notify_participants.
        "participant_reminders_enabled": True,
        "participant_reminder_template": (
            "नमस्कार, {date} रोजी {time} वाजता {place} येथे '{title}' कार्यक्रम आहे. "
            "कृपया उपस्थित रहा. - किशोरी विकास कार्यक्रम"
        ),
    },
    "report_sharing": {
        # Reports can be shared with registered users, plus these external addresses (e.g. donors).
        "allowed_external_emails": [],
    },
    "tai_targets": {
        # Default visits target for 1 Tai: 20 per week, 400 per month (admin editable)
        "weekly_visits": 20,
        "monthly_visits": 400,
        "auto_assign": True,
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


async def get_setting(db: AsyncDatabase, key: str) -> dict:
    doc = await db[c.APP_SETTINGS].find_one({"key": key})
    default = DEFAULT_SETTINGS.get(key, {})
    return _merge(default, doc["value"]) if doc else copy.deepcopy(default)


async def get_all_settings(db: AsyncDatabase) -> dict[str, dict]:
    stored = {d["key"]: d["value"] async for d in db[c.APP_SETTINGS].find()}
    return {k: _merge(v, stored.get(k, {})) for k, v in DEFAULT_SETTINGS.items()}


async def put_setting(db: AsyncDatabase, key: str, value: dict, user_id) -> tuple[dict, dict]:
    """Replace a setting. Returns (before, after) merged values for auditing."""
    before = await get_setting(db, key)
    await db[c.APP_SETTINGS].update_one(
        {"key": key},
        {"$set": {"value": value, "updated_at": utcnow(), "updated_by": user_id}},
        upsert=True,
    )
    return before, await get_setting(db, key)
