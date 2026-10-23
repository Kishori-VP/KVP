"""Case / concern management, linked to Girl IDs (PRD 4.3, 4.5)."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import Db, Pagination, require_permission, user_village_ids, village_scope, narrow_to_village
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.beneficiaries import CaseAssign, CaseCreate, CaseNote, CaseStatusChange, CaseUpdate
from app.services import audit, notifications
from app.services.app_settings import get_setting
from app.services.beneficiaries import OPEN_CASE_STATUSES, refresh_case_summary
from app.services.counters import next_case_code
from app.services.lookups import ensure_code
from app.utils.dates import to_dt, today_local, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, oids, serialize

router = APIRouter(prefix="/cases", tags=["cases"])

# Allowed status transitions. Resolved/closed always require a human-written note.
TRANSITIONS = {
    "open": {"in_progress", "escalated", "resolved", "closed"},
    "in_progress": {"escalated", "resolved", "closed", "open"},
    "escalated": {"in_progress", "resolved", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": {"in_progress"},  # re-open
}


def _case_scope(user: dict) -> dict:
    scope = village_scope(user)
    if user["role"] == Role.VOLUNTEER:
        scope["$or"] = [{"sensitive": False}, {"assigned_to": user["_id"]}]
    return scope


async def _check_assignee(db, user_id, village_id):
    assignee = await db[c.USERS].find_one({"_id": oid(user_id), "is_active": True})
    if not assignee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignee not found or inactive")
    if assignee["role"] == Role.VOLUNTEER and village_id not in user_village_ids(assignee):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Volunteer assignee must belong to the girl's village")
    return assignee


def _event(user: dict, type_: str, text: str, **extra) -> dict:
    return {"at": utcnow(), "by": user["_id"], "by_name": user.get("name"), "type": type_, "text": text, **extra}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_case(body: CaseCreate, db: Db, user: Annotated[dict, Depends(require_permission("cases", "create"))]):
    girl = await get_or_404(db[c.GIRLS], body.girl_id, "Girl", {"is_deleted": {"$ne": True}, **village_scope(user)})
    await ensure_code(db, "case_category", body.category, "category")
    if user["role"] == Role.VOLUNTEER:
        assignee = user
    else:
        assignee = await _check_assignee(db, body.assigned_to, girl["village_id"]) if body.assigned_to else None
    if body.source_type in ("home_visit", "event") and body.source_id:
        coll = c.HOME_VISITS if body.source_type == "home_visit" else c.EVENTS
        await get_or_404(db[coll], body.source_id, body.source_type.replace("_", " ").title(), village_scope(user))
    rules = await get_setting(db, "escalation_rules")
    due = body.due_date or today_local() + timedelta(days=rules["case_due_days_by_severity"][body.severity])
    now = utcnow()
    doc = {
        "case_code": await next_case_code(db),
        "girl_id": girl["_id"],
        "girl_code": girl["girl_code"],
        "village_id": girl["village_id"],
        "taluka_id": girl.get("taluka_id"),
        "category": body.category,
        "severity": body.severity,
        "status": "open",
        "title": body.title,
        "description": body.description,
        "source": {"type": body.source_type, "id": oid(body.source_id) if body.source_id else None},
        "assigned_to": assignee["_id"] if assignee else None,
        "due_date": to_dt(due),
        "next_action": body.next_action,
        "sensitive": body.sensitive,
        "timeline": [_event(user, "created", f"Case opened: {body.title}")],
        "opened_by": user["_id"],
        "opened_at": now,
        "resolved_at": None,
        "closed_at": None,
        "last_activity_at": now,
        "escalation_reminders": 0,
        "updated_at": now,
    }
    res = await db[c.CASES].insert_one(doc)
    await refresh_case_summary(db, girl["_id"])
    if assignee and assignee["_id"] != user["_id"]:
        await notifications.notify(db, assignee["_id"], "case_assigned", f"New case {doc['case_code']}",
                                   f"{body.severity.title()} {body.category} case for {girl['girl_code']}",
                                   entity_type="case", entity_id=res.inserted_id, severity=body.severity)
    await audit.log(db, user, "create", "case", res.inserted_id, f"Opened {doc['case_code']} for {girl['girl_code']}")
    return serialize(doc)


@router.get("")
async def list_cases(
    db: Db,
    user: Annotated[dict, Depends(require_permission("cases", "read"))],
    pg: Pagination,
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    category: str | None = None,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    assigned_to: ObjectIdStr | None = None,
    girl_id: ObjectIdStr | None = None,
    overdue: bool = False,
    stale: bool = Query(False, description="No activity within the configured no-update window"),
    open_only: bool = False,
):
    query: dict = _case_scope(user)
    if status_:
        query["status"] = {"$in": status_}
    elif open_only or overdue or stale:
        query["status"] = {"$in": OPEN_CASE_STATUSES}
    if severity:
        query["severity"] = {"$in": severity}
    if category:
        query["category"] = category
    narrow_to_village(query, user, village_id)
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if assigned_to:
        query["assigned_to"] = oid(assigned_to)
    if girl_id:
        query["girl_id"] = oid(girl_id)
    if overdue:
        query["due_date"] = {"$lt": to_dt(today_local())}
    if stale:
        rules = await get_setting(db, "escalation_rules")
        query["last_activity_at"] = {"$lt": utcnow() - timedelta(days=rules["case_no_update_days"])}
    total = await db[c.CASES].count_documents(query)
    docs = await db[c.CASES].find(query, {"timeline": 0}).sort([("due_date", 1)]) \
        .skip((pg.page - 1) * pg.page_size).limit(pg.page_size).to_list()
    today = to_dt(today_local())
    items = []
    for d in docs:
        out = serialize(d)
        out["is_overdue"] = d["status"] in OPEN_CASE_STATUSES and d.get("due_date") and d["due_date"] < today
        out["age_days"] = ((d.get("closed_at") or d.get("resolved_at") or utcnow()) - d["opened_at"]).days
        items.append(out)
    return {"items": items, "total": total, "page": pg.page, "page_size": pg.page_size}


@router.get("/{case_id}")
async def get_case(case_id: str, db: Db, user: Annotated[dict, Depends(require_permission("cases", "read"))]):
    case = await get_or_404(db[c.CASES], case_id, "Case", _case_scope(user))
    out = serialize(case)
    girl = await db[c.GIRLS].find_one({"_id": case["girl_id"]}, {"girl_code": 1, "name": 1, "village_id": 1})
    out["girl"] = serialize(girl)
    if case.get("assigned_to"):
        out["assignee"] = serialize(await db[c.USERS].find_one({"_id": case["assigned_to"]}, {"name": 1, "role": 1, "phone": 1}))
    out["media"] = serialize(await db[c.MEDIA].find({"entity_type": "case", "entity_id": case["_id"]}).to_list())
    return out


@router.patch("/{case_id}")
async def update_case(case_id: str, body: CaseUpdate, db: Db, user: Annotated[dict, Depends(require_permission("cases", "update"))]):
    before = await get_or_404(db[c.CASES], case_id, "Case", _case_scope(user))
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return serialize(before)
    if "category" in updates:
        await ensure_code(db, "case_category", updates["category"], "category")
    if "due_date" in updates:
        updates["due_date"] = to_dt(updates["due_date"])
    changes = diff(before, {**before, **updates})
    updates.update(updated_at=utcnow(), last_activity_at=utcnow())
    await db[c.CASES].update_one(
        {"_id": before["_id"]},
        {"$set": updates, "$push": {"timeline": _event(user, "updated", "Case details updated", changes=changes)}},
    )
    await refresh_case_summary(db, before["girl_id"])
    await audit.log(db, user, "update", "case", before["_id"], f"Updated {before['case_code']}", changes)
    return serialize(await db[c.CASES].find_one({"_id": before["_id"]}))


@router.post("/{case_id}/notes")
async def add_note(case_id: str, body: CaseNote, db: Db, user: Annotated[dict, Depends(require_permission("cases", "update"))]):
    case = await get_or_404(db[c.CASES], case_id, "Case", _case_scope(user))
    media_ids = oids(body.media_ids)
    if media_ids:
        found = await db[c.MEDIA].count_documents({"_id": {"$in": media_ids}})
        if found != len(media_ids):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown media ids")
        await db[c.MEDIA].update_many({"_id": {"$in": media_ids}}, {"$set": {"entity_type": "case", "entity_id": case["_id"]}})
    sets: dict = {"last_activity_at": utcnow(), "updated_at": utcnow()}
    if body.next_action:
        sets["next_action"] = body.next_action
    await db[c.CASES].update_one(
        {"_id": case["_id"]},
        {"$push": {"timeline": _event(user, body.type, body.text, media_ids=media_ids)}, "$set": sets},
    )
    await audit.log(db, user, "update", "case", case["_id"], f"Added {body.type} to {case['case_code']}")
    return serialize(await db[c.CASES].find_one({"_id": case["_id"]}))


@router.post("/{case_id}/status")
async def change_status(case_id: str, body: CaseStatusChange, db: Db,
                        user: Annotated[dict, Depends(require_permission("cases", "update"))]):
    case = await get_or_404(db[c.CASES], case_id, "Case", _case_scope(user))
    if body.status == case["status"]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Case is already {body.status}")
    if body.status not in TRANSITIONS[case["status"]]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Cannot move a case from {case['status']} to {body.status}")
    if body.status == "closed" and user["role"] != Role.STAKEHOLDER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Stakeholders can close cases")
    now = utcnow()
    sets: dict = {"status": body.status, "last_activity_at": now, "updated_at": now}
    if body.status == "resolved":
        sets["resolved_at"] = now
        sets["resolved_by"] = user["_id"]
    if body.status == "closed":
        sets["closed_at"] = now
        sets["closed_by"] = user["_id"]
        sets.setdefault("resolved_at", case.get("resolved_at") or now)
    if body.status in ("open", "in_progress") and case["status"] in ("resolved", "closed"):
        sets.update(resolved_at=None, closed_at=None)
    await db[c.CASES].update_one(
        {"_id": case["_id"]},
        {"$set": sets, "$push": {"timeline": _event(user, "status_change", body.note, **{"from": case["status"], "to": body.status})}},
    )
    await refresh_case_summary(db, case["girl_id"])
    if body.status == "escalated":
        await notifications.notify_stakeholders(
            db, "case_escalated", f"Case {case['case_code']} escalated", body.note,
            entity_type="case", entity_id=case["_id"], severity=case["severity"], exclude=user["_id"],
        )
    await audit.log(db, user, "status_change", "case", case["_id"], f"{case['case_code']}: {case['status']} -> {body.status}",
                    {"status": {"from": case["status"], "to": body.status}}, {"note": body.note})
    return serialize(await db[c.CASES].find_one({"_id": case["_id"]}))


@router.post("/{case_id}/assign")
async def assign_case(case_id: str, body: CaseAssign, db: Db, user: Annotated[dict, Depends(require_permission("cases", "update"))]):
    case = await get_or_404(db[c.CASES], case_id, "Case", _case_scope(user))
    if user["role"] != Role.STAKEHOLDER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Stakeholders can assign cases")
    assignee = await _check_assignee(db, body.assigned_to, case["village_id"])
    sets: dict = {"assigned_to": assignee["_id"], "last_activity_at": utcnow(), "updated_at": utcnow()}
    if body.due_date:
        sets["due_date"] = to_dt(body.due_date)
    if body.next_action:
        sets["next_action"] = body.next_action
    await db[c.CASES].update_one(
        {"_id": case["_id"]},
        {"$set": sets, "$push": {"timeline": _event(user, "assignment", f"Assigned to {assignee['name']}",
                                                    assigned_to=assignee["_id"])}},
    )
    await notifications.notify(db, assignee["_id"], "case_assigned", f"Case {case['case_code']} assigned to you",
                               body.next_action or case["title"], entity_type="case", entity_id=case["_id"],
                               severity=case["severity"])
    await audit.log(db, user, "update", "case", case["_id"], f"Assigned {case['case_code']} to {assignee['name']}",
                    {"assigned_to": {"from": case.get("assigned_to"), "to": assignee["_id"]}})
    return serialize(await db[c.CASES].find_one({"_id": case["_id"]}))
