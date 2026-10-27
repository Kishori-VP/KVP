"""Beneficiary / Girl management (PRD 4.3)."""

import re
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import ADMIN_ROLES, Db, Pagination, Stakeholder, can_access_village, group_villages, require_permission, user_village_ids, village_scope, narrow_to_village
from app.core.permissions import Role
from app.db import collections as c
from app.schemas.beneficiaries import DuplicateCheck, GirlCreate, GirlUpdate, HealthRecordCreate, MergeRequest, TransferToExternalRequest
from app.services import audit
from app.services.app_settings import get_setting
from app.services.beneficiaries import (
    AGE_BANDS,
    age_band,
    anaemia_status,
    birth_year_range_for_band,
    current_age,
    estimate_birth_year,
    find_duplicates,
    refresh_case_summary,
    refresh_health_summary,
)
from app.services.counters import next_girl_code
from app.services.lookups import ensure_code
from app.services.validation import validate_entity
from app.utils.dates import to_date, to_dt, today_local, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, serialize
from app.utils.survey_i18n import survey_in_english
from app.utils.translit import to_latin

router = APIRouter(prefix="/girls", tags=["girls"])

PARTICIPATION_ACTIVE_DAYS = 90


def girl_out(doc: dict) -> dict:
    out = serialize(doc)
    age = current_age(doc)
    out["current_age"] = age
    out["age_band"] = age_band(age)
    return out


async def _resolve_refs(db, data: dict, user: dict) -> dict:
    """Validate village/group/lookup references and convert ids. Mutates and returns data."""
    if data.get("village_id"):
        village = await get_or_404(db[c.VILLAGES], data["village_id"], "Village")
        if user["role"] == Role.VOLUNTEER and not can_access_village(user, village["_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only manage girls of your assigned villages")
        data["village_id"] = village["_id"]
        data["taluka_id"] = village["taluka_id"]
    if data.get("group_id"):
        group = await get_or_404(db[c.GROUPS], data["group_id"], "Group")
        if data.get("village_id") and data["village_id"] not in group_villages(group):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Group does not belong to the girl's village")
        data["group_id"] = group["_id"]
    if data.get("bal_panchayat_id"):
        bp = await get_or_404(db[c.GROUPS], data["bal_panchayat_id"], "Bal Panchayat")
        if bp.get("group_type") != "bal_panchayat":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This group is not a Bal Panchayat")
        if data.get("village_id") and data["village_id"] not in group_villages(bp):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Bal Panchayat does not belong to the girl's village")
        data["bal_panchayat_id"] = bp["_id"]
    if data.get("school_status"):
        await ensure_code(db, "school_status", data["school_status"], "school_status")
    for key in ("dob",):
        if key in data:
            data[key] = to_dt(data[key])
    if data.get("enrollment") and data["enrollment"].get("enrolled_on"):
        data["enrollment"]["enrolled_on"] = to_dt(data["enrollment"]["enrolled_on"])
    return data


def _probe(data: dict) -> dict:
    probe = dict(data)
    probe["dob"] = to_date(data.get("dob"))
    probe["_age"] = current_age({"dob": data.get("dob"), "birth_year": data.get("birth_year")}) \
        if (data.get("dob") or data.get("birth_year")) else data.get("age")
    return probe


def _duplicates_out(found: list) -> list:
    return [
        {"girl": girl_out(r["girl"]), "score": r["score"], "matched_fields": r["matched_fields"]} for r in found
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_girl(body: GirlCreate, db: Db, user: Annotated[dict, Depends(require_permission("girls", "create"))]):
    # Girl registration is a field-work action, not a Stakeholder action.
    if user.get("role") == Role.STAKEHOLDER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Volunteers can register girls")
    assigned = user_village_ids(user)
    if not assigned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account has no assigned village. Contact a Stakeholder.")
    data = body.model_dump(exclude={"confirm_not_duplicate", "survey_date"})
    # Never trust the client-supplied village for a Volunteer. It must be one of her villages.
    if data.get("village_id"):
        if oid(data["village_id"]) not in assigned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only register girls in your assigned villages")
    elif len(assigned) == 1:
        data["village_id"] = str(assigned[0])
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose the girl's village")
    await validate_entity(db, "girl", data)
    data = await _resolve_refs(db, data, user)
    data["birth_year"] = estimate_birth_year(body.dob, body.age, today_local())

    duplicates = await find_duplicates(db, _probe(data))
    if duplicates and not body.confirm_not_duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Possible duplicate beneficiaries found. Review them, or resubmit with "
                        "confirm_not_duplicate=true.", "candidates": serialize(_duplicates_out(duplicates))},
        )
    now = utcnow()
    village = await db[c.VILLAGES].find_one({"_id": data["village_id"]})
    girl_code, girl_seq = await next_girl_code(db, village)
    data.update(
        name_en=to_latin(data.get("name")),
        girl_code=girl_code,
        girl_seq=girl_seq,
        survey_date=to_dt(body.survey_date or today_local()),
        enrollment=data.get("enrollment") or {"status": "active", "enrolled_on": to_dt(today_local()), "exit_reason": None},
        household=data.get("household") or {},
        custom_fields=data.get("custom_fields") or {},
        case_summary={"total": 0, "open": 0, "statuses": [], "open_categories": [], "has_critical_open": False},
        health_summary=None,
        last_participation_at=None,
        flags={"profile_incomplete": not (body.name and (body.dob or body.age)), "needs_review": False},
        source="app",
        is_deleted=False,
        created_by=user["_id"],
        created_at=now,
        updated_at=now,
    )
    res = await db[c.GIRLS].insert_one(data)
    await audit.log(db, user, "create", "girl", res.inserted_id, f"Registered {data['girl_code']}",
                    meta={"possible_duplicates_overridden": len(duplicates)} if duplicates else None)
    return girl_out(data)


@router.post("/check-duplicates")
async def check_duplicates(body: DuplicateCheck, db: Db, user: Annotated[dict, Depends(require_permission("girls", "read"))]):
    data = body.model_dump(exclude={"exclude_id"})
    data["village_id"] = oid(body.village_id) if body.village_id else None
    if user["role"] == Role.VOLUNTEER and not can_access_village(user, data["village_id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only check duplicates in your assigned villages")
    data["group_id"] = oid(body.group_id) if body.group_id else None
    found = await find_duplicates(db, _probe(data), oid(body.exclude_id) if body.exclude_id else None)
    return {"candidates": _duplicates_out(found)}


@router.get("/duplicates")
async def scan_duplicates(db: Db, _: Stakeholder, village_id: ObjectIdStr, limit: int = 50):
    """Scan one village for likely duplicate pairs (useful after bulk imports)."""
    girls = await db[c.GIRLS].find({"village_id": oid(village_id), "is_deleted": {"$ne": True}, "name": {"$ne": None}}).to_list()
    pairs, seen = [], set()
    for g in girls:
        found = await find_duplicates(db, _probe(g), exclude_id=g["_id"])
        for r in found:
            key = tuple(sorted([str(g["_id"]), str(r["girl"]["_id"])]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"a": girl_out(g), "b": girl_out(r["girl"]), "score": r["score"], "matched_fields": r["matched_fields"]})
    pairs.sort(key=lambda p: -p["score"])
    return {"pairs": pairs[:limit], "total_pairs": len(pairs)}


@router.get("")
async def list_girls(
    db: Db,
    user: Annotated[dict, Depends(require_permission("girls", "read"))],
    pg: Pagination,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    group_id: ObjectIdStr | None = None,
    no_group: bool = False,
    school_status: str | None = None,
    age_band_: Annotated[Literal["below_10", "10_14", "15_19", "20_plus"] | None, Query(alias="age_band")] = None,
    min_age: int | None = None,
    max_age: int | None = None,
    participation: Literal["active", "inactive", "never"] | None = Query(
        None, description=f"active = participated in last {PARTICIPATION_ACTIVE_DAYS} days"
    ),
    enrollment_status: str | None = None,
    case_status: str | None = Query(None, description="'open', 'none', or a specific case status"),
    anaemia: str | None = Query(None, description="severe|moderate|mild|normal|unscreened"),
    profile_incomplete: bool | None = None,
    q: str | None = Query(None, description="Search by name, Girl ID or parent name"),
    sort: Literal["girl_code", "name", "created_at", "last_participation_at"] = "girl_code",
):
    query: dict = {"is_deleted": {"$ne": True}, **village_scope(user)}
    narrow_to_village(query, user, village_id)
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if group_id:  # a Kishori group, or a Bal Panchayat she belongs to
        query.setdefault("$and", []).append({"$or": [{"group_id": oid(group_id)}, {"bal_panchayat_id": oid(group_id)}]})
    elif no_group:
        query["group_id"] = None
    if school_status:
        query["school_status"] = school_status
    if age_band_:
        lo, hi = birth_year_range_for_band(age_band_)
        query["birth_year"] = {"$gte": lo, "$lte": hi}
    elif min_age is not None or max_age is not None:
        year = today_local().year
        query["birth_year"] = {"$gte": year - (max_age if max_age is not None else 99),
                               "$lte": year - (min_age if min_age is not None else 0)}
    if participation:
        cutoff = to_dt(today_local() - timedelta(days=PARTICIPATION_ACTIVE_DAYS))
        query["last_participation_at"] = {
            "active": {"$gte": cutoff}, "inactive": {"$lt": cutoff, "$ne": None}, "never": None
        }[participation]
    if enrollment_status:
        query["enrollment.status"] = enrollment_status
    if case_status == "open":
        query["case_summary.open"] = {"$gt": 0}
    elif case_status == "none":
        query["case_summary.total"] = {"$in": [0, None]}
    elif case_status:
        query["case_summary.statuses"] = case_status
    if anaemia == "unscreened":
        query["health_summary.latest_hb"] = None
    elif anaemia:
        query["health_summary.anaemia_status"] = anaemia
    if profile_incomplete is not None:
        query["flags.profile_incomplete"] = profile_incomplete
    if q:
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"name": rx}, {"name_en": rx}, {"girl_code": rx}, {"household.father_name": rx},
                        {"household.mother_name": rx}, {"household.head_name": rx}]

    sort_dir = -1 if sort in ("created_at", "last_participation_at") else 1
    total = await db[c.GIRLS].count_documents(query)
    projection = {"custom_fields.baseline_survey": 0}  # full survey answers are only sent on the profile
    cursor = db[c.GIRLS].find(query, projection).sort(sort, sort_dir)
    if sort == "girl_code":
        cursor = db[c.GIRLS].find(query, projection).sort([("girl_seq", 1), ("girl_code", 1)])
    docs = await cursor.skip((pg.page - 1) * pg.page_size).limit(pg.page_size).to_list()
    villages = await _names(db, c.VILLAGES, {d.get("village_id") for d in docs})
    groups = await _names(db, c.GROUPS, {g for d in docs for g in (d.get("group_id"), d.get("bal_panchayat_id"))})
    items = []
    for d in docs:
        caste = (d.get("custom_fields") or {}).get("caste")
        items.append({**girl_out(d), "village": villages.get(d.get("village_id")), "group": groups.get(d.get("group_id")),
                      "bal_panchayat": groups.get(d.get("bal_panchayat_id")),
                      "caste_en": to_latin(caste) if caste else None})
    return {"items": items, "total": total, "page": pg.page, "page_size": pg.page_size, "age_bands": list(AGE_BANDS)}


async def _names(db, coll: str, ids: set) -> dict:
    """Names of villages/groups in both languages, keyed by id."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    docs = await db[coll].find({"_id": {"$in": ids}}, {"name": 1, "name_mr": 1, "name_en": 1}).to_list()
    return {d["_id"]: serialize(d) for d in docs}


@router.get("/{girl_id}")
async def get_girl(girl_id: str, db: Db, user: Annotated[dict, Depends(require_permission("girls", "read"))]):
    girl = await get_or_404(db[c.GIRLS], girl_id, "Girl", {"is_deleted": {"$ne": True}, **village_scope(user)})
    out = girl_out(girl)
    village = await db[c.VILLAGES].find_one({"_id": girl.get("village_id")}, {"name": 1, "name_mr": 1})
    group = await db[c.GROUPS].find_one({"_id": girl.get("group_id")}, {"name": 1, "group_type": 1}) \
        if girl.get("group_id") else None
    out["village"] = serialize(village)
    out["group"] = serialize(group)
    bp = await db[c.GROUPS].find_one({"_id": girl["bal_panchayat_id"]}, {"name": 1, "name_en": 1})         if girl.get("bal_panchayat_id") else None
    out["bal_panchayat"] = serialize(bp)
    survey = (girl.get("custom_fields") or {}).get("baseline_survey")
    if survey:
        out["baseline_survey_en"] = survey_in_english(survey)
    caste = (girl.get("custom_fields") or {}).get("caste")
    out["caste_en"] = to_latin(caste) if caste else None
    out["participation"] = await _participation_counts(db, girl["_id"])
    case_query = {"girl_id": girl["_id"]}
    if user["role"] == Role.VOLUNTEER:
        case_query["$or"] = [{"sensitive": False}, {"assigned_to": user["_id"]}]
    out["recent_cases"] = serialize(
        await db[c.CASES].find(case_query, {"timeline": 0}).sort("opened_at", -1).limit(5).to_list()
    )
    out["recent_health"] = serialize(
        await db[c.HEALTH_RECORDS].find({"girl_id": girl["_id"]}).sort("recorded_on", -1).limit(3).to_list()
    )
    return out


async def _participation_counts(db, girl_id) -> dict:
    events_attended = await db[c.EVENTS].count_documents(
        {"attendance": {"$elemMatch": {"girl_id": girl_id, "present": True}}, "status": "completed"}
    )
    events_invited = await db[c.EVENTS].count_documents({"attendance.girl_id": girl_id, "status": "completed"})
    home_visits = await db[c.HOME_VISITS].count_documents({"girl_ids": girl_id, "status": "completed"})
    reports = await db[c.ACTIVITY_REPORTS].count_documents({"home_visit_girl_ids": girl_id})
    return {
        "events_attended": events_attended,
        "events_recorded": events_invited,
        "attendance_rate": round(events_attended / events_invited, 2) if events_invited else None,
        "home_visits": home_visits + reports,
    }


@router.get("/{girl_id}/participation")
async def participation_history(girl_id: str, db: Db, user: Annotated[dict, Depends(require_permission("girls", "read"))]):
    """Chronological history across events, meetings and home visits."""
    girl = await get_or_404(db[c.GIRLS], girl_id, "Girl", village_scope(user))
    gid = girl["_id"]
    items = []
    async for ev in db[c.EVENTS].find({"attendance.girl_id": gid, **village_scope(user)}, {"title": 1, "event_type": 1, "start_at": 1,
                                                                   "status": 1, "attendance.$": 1}):
        att = ev.get("attendance", [{}])[0]
        items.append({"type": "event", "date": ev["start_at"], "id": ev["_id"], "title": ev["title"],
                      "event_type": ev["event_type"], "present": att.get("present"), "event_status": ev["status"]})
    async for hv in db[c.HOME_VISITS].find({"girl_ids": gid, **village_scope(user)}, {"visit_date": 1, "purpose": 1, "status": 1,
                                                              "volunteer_id": 1, "observations": 1}):
        items.append({"type": "home_visit", "date": hv["visit_date"], "id": hv["_id"], "purpose": hv["purpose"],
                      "visit_status": hv["status"], "observations": hv.get("observations")})
    async for rp in db[c.ACTIVITY_REPORTS].find({"home_visit_girl_ids": gid, **village_scope(user)}, {"report_date": 1, "volunteer_id": 1}):
        items.append({"type": "home_visit_report", "date": rp["report_date"], "id": rp["_id"]})
    async for hr in db[c.HEALTH_RECORDS].find({"girl_id": gid, **village_scope(user)}, {"recorded_on": 1, "source": 1, "hb_level": 1}):
        items.append({"type": "health_check", "date": hr["recorded_on"], "id": hr["_id"], "source": hr["source"],
                      "hb_level": hr.get("hb_level")})
    items.sort(key=lambda x: x["date"], reverse=True)
    return {"girl_code": girl["girl_code"], "items": serialize(items)}


@router.patch("/{girl_id}")
async def update_girl(girl_id: str, body: GirlUpdate, db: Db, user: Annotated[dict, Depends(require_permission("girls", "update"))]):
    before = await get_or_404(db[c.GIRLS], girl_id, "Girl", {"is_deleted": {"$ne": True}, **village_scope(user)})
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return girl_out(before)
    if "village_id" in updates and user["role"] not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Stakeholders and Admins can move a girl to another village")
    if "village_id" in updates and "group_id" not in updates and before.get("group_id"):
        updates["group_id"] = None  # old group belongs to the old village
    if "village_id" in updates and "bal_panchayat_id" not in updates and before.get("bal_panchayat_id"):
        updates["bal_panchayat_id"] = None
    merged_village = updates.get("village_id") or before.get("village_id")
    data = await _resolve_refs(db, {**updates, "village_id": merged_village}, user)
    if "village_id" not in updates:
        data.pop("village_id", None)
        data.pop("taluka_id", None)
    if "dob" in updates or "age" in updates:
        dob = to_date(data.get("dob", before.get("dob")))
        age = updates.get("age", None)
        data["birth_year"] = estimate_birth_year(dob, age, today_local()) or before.get("birth_year")
    await validate_entity(db, "girl", {**before, **data})
    merged = {**before, **data}
    data["flags.profile_incomplete"] = not (merged.get("name") and (merged.get("dob") or merged.get("birth_year")))
    if "name" in data:
        data["name_en"] = to_latin(data["name"])
    data["updated_at"] = utcnow()
    await db[c.GIRLS].update_one({"_id": before["_id"]}, {"$set": data})
    after = await db[c.GIRLS].find_one({"_id": before["_id"]})
    await audit.log(db, user, "update", "girl", before["_id"], f"Updated {before['girl_code']}", diff(before, after))
    return girl_out(after)


async def _execute_transfer_to_external(
    db: Db,
    girl: dict,
    user: dict,
    reason: str,
    notes: str | None = None,
    ext_status: str = "active",
    phone: str | None = None,
    alt_phone: str | None = None,
    location: str | None = None,
    guardian_name: str | None = None,
    guardian_relation: str | None = None,
    education_status: str | None = None,
    school_or_college: str | None = None,
    standard: str | None = None,
) -> dict:
    """Execute removal from village Kishori database and transfer into External Girls."""
    now = utcnow()
    village_name = ""
    if girl.get("village_id"):
        v = await db[c.VILLAGES].find_one({"_id": girl["village_id"]})
        if v:
            village_name = v.get("name_mr") or v.get("name") or v.get("name_en") or ""

    h = girl.get("household") or {}
    resolved_phone = phone or girl.get("phone") or h.get("phone")
    resolved_alt = alt_phone or (h.get("phone") if (resolved_phone and h.get("phone") != resolved_phone) else None)

    resolved_loc = location
    if not resolved_loc:
        addr = h.get("address") or h.get("hamlet")
        resolved_loc = f"{village_name}, {addr}".strip(", ") if addr else village_name

    resolved_guardian = guardian_name or h.get("guardian_name") or h.get("father_name") or h.get("mother_name") or h.get("head_name")
    resolved_relation = guardian_relation or ("father" if h.get("father_name") else ("mother" if h.get("mother_name") else None))

    age = current_age(girl) or girl.get("age")
    dob = to_dt(girl.get("dob")) if girl.get("dob") else None

    notes_parts = [
        f"Transferred from village Kishori group ({girl.get('girl_code')}). Reason: {reason}"
    ]
    if notes:
        notes_parts.append(notes)
    combined_notes = "\n".join(notes_parts)

    ext_doc = {
        "name": girl.get("name"),
        "name_en": girl.get("name_en") or to_latin(girl.get("name", "")),
        "phone": resolved_phone,
        "alt_phone": resolved_alt,
        "age": age,
        "dob": dob,
        "location": resolved_loc,
        "guardian_name": resolved_guardian,
        "guardian_relation": resolved_relation,
        "education_status": education_status or girl.get("school_status"),
        "school_or_college": school_or_college or girl.get("school_name"),
        "standard": standard or girl.get("standard"),
        "status": ext_status,
        "notes": combined_notes,
        "call_summary": {
            "total_calls": 0,
            "last_call_at": None,
            "last_call_status": None,
            "last_caller_name": None,
        },
        "transferred_from_girl_id": girl["_id"],
        "transferred_from_girl_code": girl.get("girl_code"),
        "transferred_from_village_id": girl.get("village_id"),
        "transferred_from_village_name": village_name,
        "transferred_at": now,
        "transferred_by": user["_id"],
        "transferred_by_name": user.get("name") or user.get("username"),
        "transfer_reason": reason,
        "is_deleted": False,
        "created_by": user["_id"],
        "created_by_name": user.get("name") or user.get("username"),
        "created_at": now,
        "updated_at": now,
    }

    res_ext = await db[c.EXTERNAL_GIRLS].insert_one(ext_doc)
    ext_id = res_ext.inserted_id

    # Update girl in main database to be removed from village list
    await db[c.GIRLS].update_one(
        {"_id": girl["_id"]},
        {
            "$set": {
                "is_deleted": True,
                "deleted_at": now,
                "deleted_by": user["_id"],
                "delete_reason": f"Transferred to External Girls: {reason}",
                "transfer_reason": reason,
                "transferred_to_external_id": ext_id,
                "transferred_at": now,
                "transferred_by": user["_id"],
                "enrollment.status": "transferred",
                "enrollment.exit_reason": f"Transferred to External: {reason}",
                "enrollment.exit_date": now,
                "updated_at": now,
            }
        },
    )

    await audit.log(
        db,
        user,
        "status_change",
        "girl",
        girl["_id"],
        f"Transferred {girl.get('girl_code')} to External Girls: {reason}",
        meta={
            "external_girl_id": str(ext_id),
            "reason": reason,
            "transfer_type": "to_external",
        },
    )
    await audit.log(
        db,
        user,
        "create",
        "external_girl",
        ext_id,
        f"Transferred girl {ext_doc['name']} from {girl.get('girl_code')} ({village_name})",
        meta={"transferred_from_girl_id": str(girl["_id"]), "reason": reason},
    )

    return ext_doc


@router.post("/{girl_id}/transfer", status_code=status.HTTP_200_OK)
@router.post("/{girl_id}/transfer-to-external", status_code=status.HTTP_200_OK)
async def transfer_girl_to_external(
    girl_id: str,
    body: TransferToExternalRequest,
    db: Db,
    user: Annotated[dict, Depends(require_permission("girls", "update"))],
):
    """Remove a girl from village Kishori database and transfer her to External Girls with reason.

    She will no longer require in-person volunteer visits, but remains in the system
    as an External Girl for outreach calls and support.
    """
    girl = await get_or_404(db[c.GIRLS], girl_id, "Girl", {"is_deleted": {"$ne": True}, **village_scope(user)})
    ext_doc = await _execute_transfer_to_external(
        db=db,
        girl=girl,
        user=user,
        reason=body.reason,
        notes=body.notes,
        ext_status=body.status,
        phone=body.phone,
        alt_phone=body.alt_phone,
        location=body.location,
        guardian_name=body.guardian_name,
        guardian_relation=body.guardian_relation,
        education_status=body.education_status,
        school_or_college=body.school_or_college,
        standard=body.standard,
    )
    return {
        "message": "Girl transferred to External Girls successfully",
        "external_girl_id": str(ext_doc["_id"]),
        "external_girl": serialize(ext_doc),
    }


@router.post("/{girl_id}/merge")
async def merge_duplicate(girl_id: str, body: MergeRequest, db: Db, actor: Stakeholder):
    """Merge a duplicate record into this (primary) girl, re-linking all history."""
    from app.core.deps import check_can_delete
    check_can_delete(actor)
    primary = await get_or_404(db[c.GIRLS], girl_id, "Girl", {"is_deleted": {"$ne": True}})
    dup = await get_or_404(db[c.GIRLS], body.duplicate_id, "Duplicate girl", {"is_deleted": {"$ne": True}})
    if primary["_id"] == dup["_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot merge a record into itself")
    p, d = primary["_id"], dup["_id"]
    await db[c.HEALTH_RECORDS].update_many({"girl_id": d}, {"$set": {"girl_id": p}})
    await db[c.CASES].update_many({"girl_id": d}, {"$set": {"girl_id": p}})
    await db[c.MEDIA].update_many({"entity_type": "girl", "entity_id": d}, {"$set": {"entity_id": p}})
    for coll, field in ((c.HOME_VISITS, "girl_ids"), (c.ACTIVITY_REPORTS, "home_visit_girl_ids")):
        await db[coll].update_many({field: d}, {"$addToSet": {field: p}})
        await db[coll].update_many({field: d}, {"$pull": {field: d}})
    await db[c.EVENTS].update_many(
        {"attendance.girl_id": d},
        {"$set": {"attendance.$[a].girl_id": p}}, array_filters=[{"a.girl_id": d}],
    )
    # Fill gaps in the primary profile from the duplicate.
    fill = {k: dup[k] for k in ("name", "dob", "birth_year", "group_id", "school_status", "school_name", "phone")
            if not primary.get(k) and dup.get(k)}
    for k, v in (dup.get("household") or {}).items():
        if v and not (primary.get("household") or {}).get(k):
            fill[f"household.{k}"] = v
    if fill:
        await db[c.GIRLS].update_one({"_id": p}, {"$set": fill})
    await db[c.GIRLS].update_one(
        {"_id": d},
        {"$set": {"is_deleted": True, "merged_into": p, "deleted_at": utcnow(), "deleted_by": actor["_id"],
                  "delete_reason": f"Merged into {primary['girl_code']}: {body.reason}"}},
    )
    await db[c.GIRLS].update_one({"_id": p}, {"$max": {"last_participation_at": dup.get("last_participation_at")}})
    await refresh_case_summary(db, p)
    await refresh_health_summary(db, p)
    await audit.log(db, actor, "update", "girl", p, f"Merged {dup['girl_code']} into {primary['girl_code']}",
                    meta={"duplicate_id": d, "reason": body.reason, "fields_filled": list(fill)})
    return girl_out(await db[c.GIRLS].find_one({"_id": p}))


# ---------------------------------------------------------------- health

@router.get("/{girl_id}/health")
async def list_health(girl_id: str, db: Db, user: Annotated[dict, Depends(require_permission("health", "read"))]):
    girl = await get_or_404(db[c.GIRLS], girl_id, "Girl", village_scope(user))
    records = await db[c.HEALTH_RECORDS].find({"girl_id": girl["_id"]}).sort("recorded_on", -1).to_list()
    return {"girl_code": girl["girl_code"], "summary": serialize(girl.get("health_summary")), "records": serialize(records)}


@router.post("/{girl_id}/health", status_code=status.HTTP_201_CREATED)
async def add_health_record(girl_id: str, body: HealthRecordCreate, db: Db,
                            user: Annotated[dict, Depends(require_permission("health", "create"))]):
    girl = await get_or_404(db[c.GIRLS], girl_id, "Girl", {"is_deleted": {"$ne": True}, **village_scope(user)})
    fields = {d["code"]: d async for d in db[c.LOOKUPS].find({"type": "health_field", "is_active": True})}
    errors = []
    for key, value in body.observations.items():
        f = fields.get(key)
        if not f:
            errors.append(f"Unknown health field '{key}'")
            continue
        dtype = f.get("attributes", {}).get("data_type")
        if dtype == "number" and not isinstance(value, (int, float)):
            errors.append(f"'{key}' must be a number")
        elif dtype == "boolean" and not isinstance(value, bool):
            errors.append(f"'{key}' must be true/false")
        elif dtype == "select" and value not in f.get("attributes", {}).get("options", []):
            errors.append(f"'{key}' must be one of {f['attributes'].get('options')}")
    for code, f in fields.items():
        if f.get("attributes", {}).get("required") and code not in body.observations:
            errors.append(f"'{code}' is required")
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"validation_errors": errors})

    thresholds = await get_setting(db, "anaemia_thresholds")
    bmi = round(body.weight_kg / (body.height_cm / 100) ** 2, 1) if body.weight_kg and body.height_cm else None
    doc = {
        **body.model_dump(exclude={"event_id"}),
        "recorded_on": to_dt(body.recorded_on),
        "event_id": oid(body.event_id) if body.event_id else None,
        "girl_id": girl["_id"],
        "village_id": girl.get("village_id"),
        "anaemia_status": anaemia_status(body.hb_level, thresholds),
        "bmi": bmi,
        "recorded_by": user["_id"],
        "created_at": utcnow(),
    }
    res = await db[c.HEALTH_RECORDS].insert_one(doc)
    await refresh_health_summary(db, girl["_id"])
    await audit.log(db, user, "create", "health_record", res.inserted_id, f"Health record for {girl['girl_code']}")
    return serialize(doc)


@router.get("/{girl_id}/cases")
async def girl_cases(girl_id: str, db: Db, user: Annotated[dict, Depends(require_permission("cases", "read"))]):
    girl = await get_or_404(db[c.GIRLS], girl_id, "Girl", village_scope(user))
    query: dict = {"girl_id": girl["_id"]}
    if user["role"] == Role.VOLUNTEER:
        query["$or"] = [{"sensitive": False}, {"assigned_to": user["_id"]}]
    cases = await db[c.CASES].find(query).sort("opened_at", -1).to_list()
    return {"girl_code": girl["girl_code"], "cases": serialize(cases)}
