"""Home visits and daily activity reports.

Mobile field forms support GPS capture, voice input and offline queue retries; these endpoints also provide
Stakeholders the records that feed targets,
dashboards and reports, plus planning (upcoming visits) and approvals.
"""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.deps import Db, Pagination, Stakeholder, ADMIN_ROLES, require_permission, user_village_ids, village_scope, narrow_to_village
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.beneficiaries import ActivityReportCreate, ApprovalDecision, HomeVisitCreate, HomeVisitUpdate
from app.services import audit
from app.services.beneficiaries import touch_participation
from app.services.lookups import ensure_code
from app.services.validation import validate_entity
from app.utils.dates import day_range, to_dt, today_local, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, oids, paginate, serialize

router = APIRouter(tags=["field activity"])


async def _volunteer(db, volunteer_id, user: dict) -> dict:
    vol = await db[c.USERS].find_one({"_id": oid(volunteer_id), "role": Role.VOLUNTEER.value})
    if not vol:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Volunteer not found")
    if not user_village_ids(vol):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Volunteer has no assigned village")
    if user["role"] == Role.VOLUNTEER and vol["_id"] != user["_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Volunteers can only record their own activity")
    return vol


async def _record_village(db, vol: dict, village_id) -> dict:
    """The village a new record belongs to: the one chosen, or her only village."""
    vids = user_village_ids(vol)
    if village_id:
        if oid(village_id) not in vids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The volunteer is not assigned to this village")
        chosen = oid(village_id)
    elif len(vids) == 1:
        chosen = vids[0]
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "The volunteer works in several villages: choose the village (village_id)")
    return await db[c.VILLAGES].find_one({"_id": chosen}, {"taluka_id": 1, "name": 1})


async def _girls_in_village(db, girl_ids: list, village_id) -> list:
    ids = oids(girl_ids)
    if ids:
        n = await db[c.GIRLS].count_documents({"_id": {"$in": ids}, "village_id": village_id, "is_deleted": {"$ne": True}})
        if n != len(set(ids)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "All girls must belong to the volunteer's village")
    return list(dict.fromkeys(ids))


def _check_date_rules(d: date, status_: str):
    today = today_local()
    if status_ == "planned" and d < today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Planned visits must be dated today or later")
    if status_ in ("completed", "missed") and d > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Past records cannot carry a future date")


# ---------------------------------------------------------------- home visits

@router.post("/home-visits", status_code=status.HTTP_201_CREATED)
async def create_home_visit(body: HomeVisitCreate, db: Db,
                            user: Annotated[dict, Depends(require_permission("home_visits", "create"))]):
    if body.client_record_id:
        existing = await db[c.HOME_VISITS].find_one({"client_record_id": body.client_record_id, "created_by": user["_id"]})
        if existing:
            return serialize(existing)
    vol = await _volunteer(db, body.volunteer_id, user)
    _check_date_rules(body.visit_date, body.status)
    village = await _record_village(db, vol, body.village_id)
    girl_ids = await _girls_in_village(db, body.girl_ids, village["_id"])
    data = body.model_dump(exclude={"volunteer_id", "village_id", "girl_ids", "visit_date"})
    await validate_entity(db, "home_visit", {**data, "volunteer_id": vol["_id"], "village_id": village["_id"],
                                             "visit_date": body.visit_date})
    now = utcnow()
    is_historical = body.is_historical or body.visit_date < today_local()
    doc = {
        **data,
        "volunteer_id": vol["_id"],
        "village_id": village["_id"],
        "taluka_id": village["taluka_id"],
        "girl_ids": girl_ids,
        "visit_date": to_dt(body.visit_date),
        "is_historical": is_historical,
        "source": "app",
        "location_flag": None if body.gps else ("missing_gps" if body.status == "completed" else None),
        "media_ids": [],
        # Admin/Stakeholder entries and live captures are auto-approved; back-dated volunteer entries need review.
        "approval": {"status": "approved" if user["role"] in ADMIN_ROLES or not is_historical else "pending",
                     "by": user["_id"] if user["role"] in ADMIN_ROLES else None,
                     "at": now if user["role"] in ADMIN_ROLES else None, "remarks": None},
        "created_by": user["_id"],
        "created_at": now,
        "updated_at": now,
    }
    try:
        res = await db[c.HOME_VISITS].insert_one(doc)
    except DuplicateKeyError:
        if body.client_record_id:
            existing = await db[c.HOME_VISITS].find_one({"client_record_id": body.client_record_id, "created_by": user["_id"]})
            if existing:
                return serialize(existing)
        raise
    if body.status == "completed":
        await touch_participation(db, girl_ids, doc["visit_date"])
    await audit.log(db, user, "create", "home_visit", res.inserted_id,
                    f"{body.status.title()} home visit on {body.visit_date}", meta={"historical": is_historical})
    return serialize(doc)


@router.get("/home-visits")
async def list_home_visits(
    db: Db,
    user: Annotated[dict, Depends(require_permission("home_visits", "read"))],
    pg: Pagination,
    volunteer_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
    girl_id: ObjectIdStr | None = None,
    status_: Annotated[Literal["planned", "completed", "missed"] | None, Query(alias="status")] = None,
    approval: Literal["pending", "approved", "rejected"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    upcoming: bool = False,
):
    query: dict = village_scope(user)
    if volunteer_id:
        query["volunteer_id"] = oid(volunteer_id)
    narrow_to_village(query, user, village_id)
    if girl_id:
        query["girl_ids"] = oid(girl_id)
    if status_:
        query["status"] = status_
    if approval:
        query["approval.status"] = approval
    if upcoming:
        query.update(status="planned", visit_date={"$gte": to_dt(today_local())})
    elif start_date or end_date:
        s, e = day_range(start_date or date(2000, 1, 1), end_date or date(2100, 1, 1))
        query["visit_date"] = {"$gte": s, "$lt": e}
    sort = [("visit_date", 1 if upcoming else -1)]
    return await paginate(db[c.HOME_VISITS], query, pg.page, pg.page_size, sort=sort)


@router.get("/home-visits/{visit_id}")
async def get_home_visit(visit_id: str, db: Db, user: Annotated[dict, Depends(require_permission("home_visits", "read"))]):
    visit = await get_or_404(db[c.HOME_VISITS], visit_id, "Home visit", village_scope(user))
    if user["role"] == Role.VOLUNTEER and visit.get("volunteer_id") != user["_id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Home visit not found")
    out = serialize(visit)
    out["girls"] = serialize(await db[c.GIRLS].find({"_id": {"$in": visit.get("girl_ids", [])}},
                                                   {"girl_code": 1, "name": 1}).to_list())
    out["media"] = serialize(await db[c.MEDIA].find({"entity_type": "home_visit", "entity_id": visit["_id"]}).to_list())
    return out


@router.patch("/home-visits/{visit_id}")
async def update_home_visit(visit_id: str, body: HomeVisitUpdate, db: Db,
                            user: Annotated[dict, Depends(require_permission("home_visits", "update"))]):
    before = await get_or_404(db[c.HOME_VISITS], visit_id, "Home visit", village_scope(user))
    if user["role"] == Role.VOLUNTEER and before.get("volunteer_id") != user["_id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Home visit not found")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return serialize(before)
    new_status = updates.get("status", before["status"])
    new_date = updates.get("visit_date") or before["visit_date"].date()
    if "status" in updates or "visit_date" in updates:
        _check_date_rules(new_date, new_status)
    if "visit_date" in updates:
        updates["visit_date"] = to_dt(updates["visit_date"])
    if "girl_ids" in updates:
        updates["girl_ids"] = await _girls_in_village(db, updates["girl_ids"], before["village_id"])
    updates["updated_at"] = utcnow()
    await db[c.HOME_VISITS].update_one({"_id": before["_id"]}, {"$set": updates})
    after = await db[c.HOME_VISITS].find_one({"_id": before["_id"]})
    if after["status"] == "completed":
        await touch_participation(db, after["girl_ids"], after["visit_date"])
    await audit.log(db, user, "update", "home_visit", before["_id"], "Updated home visit", diff(before, after))
    return serialize(after)


@router.post("/home-visits/{visit_id}/approval")
async def approve_home_visit(visit_id: str, body: ApprovalDecision, db: Db, actor: Stakeholder):
    return await _decide(db, c.HOME_VISITS, "home_visit", visit_id, body, actor)


@router.delete("/home-visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_home_visit(visit_id: str, db: Db, actor: Stakeholder, reason: str = Query(min_length=3)):
    visit = await get_or_404(db[c.HOME_VISITS], visit_id, "Home visit")
    await db[c.HOME_VISITS].delete_one({"_id": visit["_id"]})
    await audit.log(db, actor, "delete", "home_visit", visit["_id"], "Deleted home visit",
                    meta={"reason": reason, "record": serialize(visit)})


async def _decide(db, coll, entity, id_, body: ApprovalDecision, actor):
    doc = await get_or_404(db[coll], id_, entity.replace("_", " ").title())
    approval = {"status": body.decision, "by": actor["_id"], "at": utcnow(), "remarks": body.remarks}
    await db[coll].update_one({"_id": doc["_id"]}, {"$set": {"approval": approval}})
    await audit.log(db, actor, "approve" if body.decision == "approved" else "reject", entity, doc["_id"],
                    f"{body.decision.title()} {entity.replace('_', ' ')}", meta={"remarks": body.remarks})
    return serialize(await db[coll].find_one({"_id": doc["_id"]}))


# ---------------------------------------------------------------- daily activity reports

@router.post("/activity-reports", status_code=status.HTTP_201_CREATED)
async def create_activity_report(body: ActivityReportCreate, db: Db,
                                 user: Annotated[dict, Depends(require_permission("activity_reports", "create"))]):
    if body.client_record_id:
        existing = await db[c.ACTIVITY_REPORTS].find_one({"client_record_id": body.client_record_id, "submitted_by": user["_id"]})
        if existing:
            return serialize(existing)
    vol = await _volunteer(db, body.volunteer_id, user)
    if body.report_date > today_local():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Report date cannot be in the future")
    for code in body.activities:
        await ensure_code(db, "activity_type", code, "activity")
    village = await _record_village(db, vol, body.village_id)
    group_ids = oids(body.group_ids)
    if group_ids and await db[c.GROUPS].count_documents({"_id": {"$in": group_ids}, "village_id": village["_id"]}) != len(set(group_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Groups must belong to the volunteer's village")
    girl_ids = await _girls_in_village(db, body.home_visit_girl_ids, village["_id"])
    now = utcnow()
    is_historical = body.is_historical or body.report_date < today_local()
    doc = {
        **body.model_dump(exclude={"volunteer_id", "village_id", "group_ids", "home_visit_girl_ids", "report_date"}),
        "volunteer_id": vol["_id"],
        "village_id": village["_id"],
        "taluka_id": village["taluka_id"],
        "report_date": to_dt(body.report_date),
        "group_ids": group_ids,
        "home_visit_girl_ids": girl_ids,
        "is_historical": is_historical,
        "source": "app",
        "approval": {"status": "approved" if user["role"] in ADMIN_ROLES else "pending",
                     "by": user["_id"] if user["role"] in ADMIN_ROLES else None,
                     "at": now if user["role"] in ADMIN_ROLES else None, "remarks": None},
        "submitted_by": user["_id"],
        "submitted_at": now,
    }
    try:
        res = await db[c.ACTIVITY_REPORTS].insert_one(doc)
    except DuplicateKeyError:
        if body.client_record_id:
            existing = await db[c.ACTIVITY_REPORTS].find_one({"client_record_id": body.client_record_id, "submitted_by": user["_id"]})
            if existing:
                return serialize(existing)
        raise HTTPException(status.HTTP_409_CONFLICT, "A report for this volunteer and date already exists")
    await touch_participation(db, girl_ids, doc["report_date"])
    await audit.log(db, user, "create", "activity_report", res.inserted_id,
                    f"Activity report for {vol['name']} on {body.report_date}")
    return serialize(doc)


@router.get("/activity-reports")
async def list_activity_reports(
    db: Db,
    user: Annotated[dict, Depends(require_permission("activity_reports", "read"))],
    pg: Pagination,
    volunteer_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
    approval: Literal["pending", "approved", "rejected"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    query: dict = village_scope(user)
    if volunteer_id:
        query["volunteer_id"] = oid(volunteer_id)
    narrow_to_village(query, user, village_id)
    if approval:
        query["approval.status"] = approval
    if start_date or end_date:
        s, e = day_range(start_date or date(2000, 1, 1), end_date or date(2100, 1, 1))
        query["report_date"] = {"$gte": s, "$lt": e}
    return await paginate(db[c.ACTIVITY_REPORTS], query, pg.page, pg.page_size, sort=[("report_date", -1)])


@router.post("/activity-reports/{report_id}/approval")
async def approve_activity_report(report_id: str, body: ApprovalDecision, db: Db, actor: Stakeholder):
    return await _decide(db, c.ACTIVITY_REPORTS, "activity_report", report_id, body, actor)


@router.get("/activity-reports/{report_id}")
async def get_activity_report(report_id: str, db: Db,
                              user: Annotated[dict, Depends(require_permission("activity_reports", "read"))]):
    doc = await get_or_404(db[c.ACTIVITY_REPORTS], report_id, "Activity report")
    if user["role"] == Role.VOLUNTEER.value and doc.get("volunteer_id") != user["_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return serialize(doc)


@router.delete("/activity-reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity_report(report_id: str, db: Db, actor: Stakeholder, reason: str = Query("Deleted by coordinator", min_length=3)):
    report = await get_or_404(db[c.ACTIVITY_REPORTS], report_id, "Activity report")
    await db[c.ACTIVITY_REPORTS].delete_one({"_id": report["_id"]})
    await audit.log(db, actor, "delete", "activity_report", report["_id"], "Deleted activity report",
                    meta={"reason": reason, "record": serialize(report)})

