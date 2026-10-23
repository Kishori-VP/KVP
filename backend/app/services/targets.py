from datetime import date

from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.core.deps import user_village_ids
from app.services import audit, metrics
from app.services.app_settings import get_setting
from app.utils.dates import to_date, to_dt, today_local, utcnow

TARGET_STATUSES = ["upcoming", "on_track", "at_risk", "achieved", "missed", "cancelled"]


def evaluate(target: dict, achieved: int, thresholds: dict, today: date | None = None) -> dict:
    today = today or today_local()
    start, end = to_date(target["period_start"]), to_date(target["period_end"])
    value = target["target_value"]
    total_days = (end - start).days + 1
    elapsed = min(max((today - start).days + 1, 0), total_days)
    expected_now = value * elapsed / total_days if total_days else value
    progress = round(100 * achieved / value, 1) if value else 100.0

    if target.get("status") == "cancelled":
        state = "cancelled"
    elif today < start:
        state = "upcoming"
    elif achieved >= value:
        state = "achieved"
    elif today > end:
        state = "missed"
    else:
        ratio = achieved / expected_now if expected_now else 1
        state = "on_track" if ratio >= thresholds["on_track_min_ratio"] else "at_risk"

    days_left = max((end - today).days, 0) if today <= end else 0
    return {
        "achieved": achieved,
        "progress_pct": progress,
        "expected_by_now": round(expected_now, 1),
        "remaining": max(value - achieved, 0),
        "days_left": days_left,
        "elapsed_pct": round(100 * elapsed / total_days, 1) if total_days else 100.0,
        "status": state,
        "deadline_approaching": state in ("on_track", "at_risk") and days_left <= thresholds["deadline_warning_days"],
        "low_performance": state in ("at_risk", "missed")
        and (achieved / expected_now if expected_now else 1) < thresholds["low_performance_ratio"],
    }


async def with_progress(db: AsyncDatabase, targets: list[dict], thresholds: dict | None = None) -> list[dict]:
    thresholds = thresholds or await get_setting(db, "target_thresholds")
    out = []
    vol_ids = list({t["volunteer_id"] for t in targets if t.get("volunteer_id")})
    vol_villages = {}
    if vol_ids:
        from app.core.deps import user_village_ids
        async for v in db[c.USERS].find({"_id": {"$in": vol_ids}}, {"village_id": 1, "village_ids": 1}):
            vids = user_village_ids(v)
            if vids:
                vol_villages[v["_id"]] = vids

    for t in targets:
        if today_local() < to_date(t["period_start"]) or t.get("status") == "cancelled":
            achieved = 0
        else:
            vid = t.get("village_id")
            if t["volunteer_id"] in vol_villages:
                vid = vol_villages[t["volunteer_id"]]
            achieved = await metrics.compute(db, t["metric"], t["volunteer_id"], vid,
                                             to_date(t["period_start"]), to_date(t["period_end"]))
        out.append({**t, "progress": evaluate(t, achieved, thresholds)})
    return out


async def handle_reassignment(db: AsyncDatabase, volunteer: dict, old_village_id, action: str,
                              transfer_to, actor: dict, reason: str) -> dict:
    """Apply the chosen policy to the open (current/future) targets of a volunteer leaving old_village_id.

    Targets are combined across all of a volunteer's villages, so "move" keeps them with her
    (older single-village targets become combined)."""
    today = today_local()
    open_targets = await db[c.TARGETS].find({
        "volunteer_id": volunteer["_id"], "status": "active", "period_end": {"$gte": to_dt(today)},
    }).to_list()
    if not open_targets:
        return {"action": action, "affected": 0}

    new_owner = None
    if action == "transfer":
        new_owner = await db[c.USERS].find_one({"_id": transfer_to, "role": "volunteer", "is_active": True})
        if not new_owner or old_village_id not in user_village_ids(new_owner):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "Targets can only be transferred to an active volunteer of the old village")

    now = utcnow()
    changed = 0
    for t in open_targets:
        revision = {"at": now, "by": actor["_id"], "reason": f"Reassignment: {reason}", "changes": {}}
        sets: dict = {"updated_at": now}
        if action == "move":
            if not t.get("village_id"):
                continue  # already a combined target: nothing changes
            sets["village_id"] = None
            revision["changes"]["village_id"] = {"from": t["village_id"], "to": None}
        elif action == "close":
            sets.update(status="cancelled", cancel_reason=f"Volunteer reassigned: {reason}")
            revision["changes"]["status"] = {"from": "active", "to": "cancelled"}
        else:
            sets["volunteer_id"] = new_owner["_id"]
            revision["changes"]["volunteer_id"] = {"from": volunteer["_id"], "to": new_owner["_id"]}
        await db[c.TARGETS].update_one({"_id": t["_id"]}, {"$set": sets, "$push": {"revisions": revision}})
        await audit.log(db, actor, "revise", "target", t["_id"], f"Target {action} on reassignment",
                        revision["changes"], {"reason": reason})
        changed += 1
    return {"action": action, "affected": changed,
            "transferred_to": str(new_owner["_id"]) if new_owner else None}

