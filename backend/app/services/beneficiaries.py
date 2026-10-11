"""Girl-related helpers: age derivation, duplicate detection, denormalised summaries."""

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.services.app_settings import get_setting
from app.utils.dates import age_on, to_date, today_local, utcnow

OPEN_CASE_STATUSES = ["open", "in_progress", "escalated"]


def estimate_birth_year(dob: date | None, age: int | None, recorded_on: date | None) -> int | None:
    if dob:
        return dob.year
    if age is not None:
        return (recorded_on or today_local()).year - age
    return None


def current_age(girl: dict) -> int | None:
    dob = to_date(girl.get("dob"))
    if dob:
        return age_on(dob, today_local())
    if girl.get("birth_year"):
        return today_local().year - girl["birth_year"]
    return None


def age_band(age: int | None) -> str | None:
    if age is None:
        return None
    if age < 10:
        return "below_10"
    if age <= 14:
        return "10_14"
    if age <= 19:
        return "15_19"
    return "20_plus"


AGE_BANDS = {"below_10": (0, 9), "10_14": (10, 14), "15_19": (15, 19), "20_plus": (20, 99)}


def birth_year_range_for_band(band: str) -> tuple[int, int]:
    lo, hi = AGE_BANDS[band]
    year = today_local().year
    return year - hi, year - lo


def anaemia_status(hb: float | None, thresholds: dict) -> str | None:
    if hb is None:
        return None
    if hb < thresholds["severe_below"]:
        return "severe"
    if hb < thresholds["moderate_below"]:
        return "moderate"
    if hb < thresholds["mild_below"]:
        return "mild"
    return "normal"


# ---------------------------------------------------------------- duplicate detection

def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    name = unicodedata.normalize("NFC", name).lower()
    name = re.sub(r"[^\w\s]", " ", name)
    return " ".join(name.split())


def name_similarity(a: str | None, b: str | None) -> float:
    a, b = normalize_name(a), normalize_name(b)
    if not a or not b:
        return 0.0
    direct = SequenceMatcher(None, a, b).ratio()
    # Token-order independent comparison ("Pooja Raju Shinde" vs "Shinde Pooja Raju").
    sorted_ratio = SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio()
    return max(direct, sorted_ratio)


FIELD_WEIGHTS = {
    "name": 0.45,
    "village_id": 0.15,
    "age": 0.1,
    "dob": 0.15,
    "group_id": 0.05,
    "household.father_name": 0.15,
    "household.mother_name": 0.1,
    "household.head_name": 0.1,
    "household.phone": 0.15,
}


def _get(doc: dict, path: str):
    cur = doc
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def match_score(candidate: dict, probe: dict, cfg: dict) -> tuple[float, dict]:
    """Weighted similarity across configured fields where both sides have a value."""
    total_w, score, details = 0.0, 0.0, {}
    for field in cfg["fields"]:
        w = FIELD_WEIGHTS.get(field, 0.1)
        if field == "age":
            a, b = current_age(candidate), probe.get("_age")
            if a is None or b is None:
                continue
            s = 1.0 if abs(a - b) <= cfg["age_tolerance_years"] else 0.0
        elif field == "dob":
            a, b = to_date(candidate.get("dob")), probe.get("dob")
            if not a or not b:
                continue
            s = 1.0 if a == b else 0.0
        elif field in ("name", "household.father_name", "household.mother_name", "household.head_name"):
            a, b = _get(candidate, field), _get(probe, field)
            if not a or not b:
                continue
            s = name_similarity(a, b)
            if field == "name" and s < cfg["name_similarity_threshold"]:
                s *= 0.5  # weak name match should pull the overall score down hard
        else:
            a, b = _get(candidate, field), _get(probe, field)
            if a is None or b is None:
                continue
            s = 1.0 if str(a) == str(b) else 0.0
        total_w += w
        score += w * s
        details[field] = round(s, 2)
    if total_w == 0 or "name" not in details:
        return 0.0, details
    return round(score / total_w, 3), details


async def find_duplicates(db: AsyncDatabase, probe: dict, exclude_id: ObjectId | None = None, limit: int = 10) -> list:
    """probe uses storage shape: name, village_id (ObjectId), dob (date), household{}, _age (int)."""
    cfg = await get_setting(db, "duplicate_matching")
    if not probe.get("name"):
        return []
    query: dict = {"is_deleted": {"$ne": True}}
    if "village_id" in cfg["fields"] and probe.get("village_id"):
        query["village_id"] = probe["village_id"]
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    results = []
    async for cand in db[c.GIRLS].find(
        query, {"girl_code": 1, "name": 1, "dob": 1, "birth_year": 1, "village_id": 1, "group_id": 1, "household": 1}
    ):
        score, details = match_score(cand, probe, cfg)
        if score >= cfg["min_score"]:
            results.append({"girl": cand, "score": score, "matched_fields": details})
    results.sort(key=lambda r: -r["score"])
    return results[:limit]


# ---------------------------------------------------------------- denormalised summaries

async def refresh_case_summary(db: AsyncDatabase, girl_id: ObjectId) -> None:
    cases = await db[c.CASES].find({"girl_id": girl_id}, {"status": 1, "severity": 1, "category": 1}).to_list()
    open_cases = [x for x in cases if x["status"] in OPEN_CASE_STATUSES]
    await db[c.GIRLS].update_one(
        {"_id": girl_id},
        {
            "$set": {
                "case_summary": {
                    "total": len(cases),
                    "open": len(open_cases),
                    "statuses": sorted({x["status"] for x in cases}),
                    "open_categories": sorted({x["category"] for x in open_cases}),
                    "has_critical_open": any(x["severity"] == "critical" for x in open_cases),
                }
            }
        },
    )


async def touch_participation(db: AsyncDatabase, girl_ids: list[ObjectId], when) -> None:
    """Record the most recent programme participation date on each girl."""
    if not girl_ids:
        return
    await db[c.GIRLS].update_many(
        {"_id": {"$in": girl_ids}},
        {"$max": {"last_participation_at": when}, "$set": {"updated_at": utcnow()}},
    )


async def refresh_health_summary(db: AsyncDatabase, girl_id: ObjectId) -> None:
    latest = await db[c.HEALTH_RECORDS].find_one({"girl_id": girl_id}, sort=[("recorded_on", -1)])
    latest_hb = await db[c.HEALTH_RECORDS].find_one(
        {"girl_id": girl_id, "hb_level": {"$ne": None}}, sort=[("recorded_on", -1)]
    )
    summary = None
    if latest:
        summary = {
            "last_recorded_on": latest["recorded_on"],
            "latest_hb": latest_hb["hb_level"] if latest_hb else None,
            "latest_hb_on": latest_hb["recorded_on"] if latest_hb else None,
            "anaemia_status": latest_hb.get("anaemia_status") if latest_hb else None,
            "bmi": latest.get("bmi"),
        }
    await db[c.GIRLS].update_one({"_id": girl_id}, {"$set": {"health_summary": summary}})
