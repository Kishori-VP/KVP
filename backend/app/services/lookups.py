"""Configurable dropdown values (activity types, case categories, target types...)."""

from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c

LOOKUP_TYPES = {
    "activity_type": "Field activity types (home visit, group meeting, health camp...)",
    "event_type": "Event types used when scheduling events",
    "case_category": "Case / concern categories",
    "target_type": "Target types; each maps to a supported progress metric",
    "contact_category": "Village support directory contact categories",
    "school_status": "Girl school status values",
    "health_field": "Configurable health / anaemia observation fields",
}

# Metrics the target engine knows how to measure. Target types map to one of these.
TARGET_METRICS = {
    "home_visits": "Completed home visits",
    "group_meetings": "Completed Kishori / Bal Panchayat group meetings",
    "events": "Completed events (any type)",
    "girls_covered": "Distinct girls reached via visits or event attendance",
    "follow_ups": "Follow-up visits and case follow-up notes",
    "case_closures": "Cases resolved or closed",
    "health_screenings": "Health records captured",
    "activity_reports": "Daily activity reports submitted",
}

CASE_SEVERITIES = ["critical", "high", "medium", "low"]
CASE_STATUSES = ["open", "in_progress", "escalated", "resolved", "closed"]
MANDATORY_CONTACT_CATEGORIES = ["hospital_head", "police_patil", "sarpanch", "talathi"]


async def active_codes(db: AsyncDatabase, lookup_type: str) -> set[str]:
    return {d["code"] async for d in db[c.LOOKUPS].find({"type": lookup_type, "is_active": True}, {"code": 1})}


async def ensure_code(db: AsyncDatabase, lookup_type: str, code: str | None, field: str) -> None:
    if code is None:
        return
    found = await db[c.LOOKUPS].find_one({"type": lookup_type, "code": code, "is_active": True})
    if not found:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unknown {field} '{code}'. Configure it under /config/lookups ({lookup_type}).",
        )


async def get_lookup(db: AsyncDatabase, lookup_type: str, code: str) -> dict | None:
    return await db[c.LOOKUPS].find_one({"type": lookup_type, "code": code})
