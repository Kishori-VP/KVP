"""Village support directory (PRD 4.2 key contacts + 4.13)."""

import re

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, Db, Pagination, Stakeholder, require_permission, village_scope, narrow_to_village
from app.db import collections as c
from app.schemas.master import ContactCreate, ContactUpdate
from app.services import audit
from app.services.lookups import MANDATORY_CONTACT_CATEGORIES, ensure_code
from app.services.validation import validate_entity
from app.utils.dates import utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, serialize

router = APIRouter(prefix="/contacts", tags=["contacts"])
CanRead = Depends(require_permission("contacts", "read"))


def _with_actions(doc: dict) -> dict:
    out = serialize(doc)
    mobile = doc.get("mobile")
    out["quick_actions"] = (
        {"call": f"tel:+91{mobile}", "sms": f"sms:+91{mobile}", "whatsapp": f"https://wa.me/91{mobile}"}
        if mobile else None
    )
    out["is_mandatory_category"] = doc.get("category") in MANDATORY_CONTACT_CATEGORIES
    return out


async def _ensure_single_mandatory(db, village_id, category, exclude_id=None):
    if category not in MANDATORY_CONTACT_CATEGORIES:
        return
    query = {"village_id": village_id, "category": category, "is_active": True}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if await db[c.CONTACTS].find_one(query):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This village already has an active '{category}' contact. Update or deactivate it first.",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(body: ContactCreate, db: Db, actor: Stakeholder):
    village = await get_or_404(db[c.VILLAGES], body.village_id, "Village")
    await ensure_code(db, "contact_category", body.category, "category")
    data = body.model_dump()
    await validate_entity(db, "contact", data)
    await _ensure_single_mandatory(db, village["_id"], body.category)
    now = utcnow()
    doc = {
        **data,
        "village_id": village["_id"],
        "taluka_id": village["taluka_id"],
        "is_active": True,
        "verified": False,
        "verified_by": None,
        "verified_at": None,
        "created_by": actor["_id"],
        "created_at": now,
        "updated_at": now,
    }
    res = await db[c.CONTACTS].insert_one(doc)
    await audit.log(db, actor, "create", "contact", res.inserted_id, f"Added {body.category} contact {body.name}")
    return _with_actions(doc)


@router.get("", dependencies=[CanRead])
async def list_contacts(
    db: Db,
    user: CurrentUser,
    pg: Pagination,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    category: str | None = None,
    verified: bool | None = None,
    q: str | None = None,
    include_inactive: bool = False,
):
    query: dict = village_scope(user)
    narrow_to_village(query, user, village_id)
    if taluka_id:
        query["taluka_id"] = oid(taluka_id)
    if category:
        query["category"] = category
    if verified is not None:
        query["verified"] = verified
    if not include_inactive:
        query["is_active"] = True
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"designation": rx}, {"mobile": rx}, {"facility_name": rx}]
    total = await db[c.CONTACTS].count_documents(query)
    docs = await db[c.CONTACTS].find(query).sort([("village_id", 1), ("category", 1)]) \
        .skip((pg.page - 1) * pg.page_size).limit(pg.page_size).to_list()
    return {"items": [_with_actions(d) for d in docs], "total": total, "page": pg.page, "page_size": pg.page_size}


@router.get("/coverage")
async def mandatory_contact_coverage(db: Db, _: Stakeholder, taluka_id: ObjectIdStr | None = None):
    """Which villages are missing (or have unverified) mandatory key contacts."""
    vquery: dict = {"status": "active"}
    if taluka_id:
        vquery["taluka_id"] = oid(taluka_id)
    villages = await db[c.VILLAGES].find(vquery).sort("name", 1).to_list()
    contacts = await db[c.CONTACTS].find(
        {"village_id": {"$in": [v["_id"] for v in villages]}, "is_active": True,
         "category": {"$in": MANDATORY_CONTACT_CATEGORIES}}
    ).to_list()
    by_village: dict = {}
    for ct in contacts:
        by_village.setdefault(ct["village_id"], {})[ct["category"]] = ct
    rows = []
    for v in villages:
        have = by_village.get(v["_id"], {})
        rows.append({
            "village_id": str(v["_id"]),
            "village_name": v["name"],
            "village_name_mr": v.get("name_mr"),
            "missing": [cat for cat in MANDATORY_CONTACT_CATEGORIES if cat not in have],
            "unverified": [cat for cat, ct in have.items() if not ct.get("verified")],
            "complete": len(have) == len(MANDATORY_CONTACT_CATEGORIES)
            and all(ct.get("verified") for ct in have.values()),
        })
    return {
        "mandatory_categories": MANDATORY_CONTACT_CATEGORIES,
        "villages_complete": sum(r["complete"] for r in rows),
        "villages_total": len(rows),
        "villages": rows,
    }


@router.get("/{contact_id}", dependencies=[CanRead])
async def get_contact(contact_id: str, db: Db, user: CurrentUser):
    return _with_actions(await get_or_404(db[c.CONTACTS], contact_id, "Contact", village_scope(user)))


@router.patch("/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate, db: Db, actor: Stakeholder):
    before = await get_or_404(db[c.CONTACTS], contact_id, "Contact")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _with_actions(before)
    if "category" in updates:
        await ensure_code(db, "contact_category", updates["category"], "category")
    merged = {**before, **updates}
    await validate_entity(db, "contact", merged)
    if merged.get("is_active"):
        await _ensure_single_mandatory(db, before["village_id"], merged["category"], before["_id"])
    # Any change to the person's details invalidates the previous verification.
    if {"name", "mobile", "alternate_mobile", "category"} & updates.keys():
        updates.update(verified=False, verified_by=None, verified_at=None)
    updates["updated_at"] = utcnow()
    await db[c.CONTACTS].update_one({"_id": before["_id"]}, {"$set": updates})
    after = await db[c.CONTACTS].find_one({"_id": before["_id"]})
    await audit.log(db, actor, "update", "contact", before["_id"], f"Updated contact {after['name']}", diff(before, after))
    return _with_actions(after)


@router.post("/{contact_id}/verify")
async def verify_contact(contact_id: str, db: Db, actor: Stakeholder):
    contact = await get_or_404(db[c.CONTACTS], contact_id, "Contact")
    now = utcnow()
    await db[c.CONTACTS].update_one(
        {"_id": contact["_id"]}, {"$set": {"verified": True, "verified_by": actor["_id"], "verified_at": now}}
    )
    await audit.log(db, actor, "verify", "contact", contact["_id"], f"Verified contact {contact['name']}")
    return _with_actions(await db[c.CONTACTS].find_one({"_id": contact["_id"]}))


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: str, db: Db, actor: Stakeholder):
    contact = await get_or_404(db[c.CONTACTS], contact_id, "Contact")
    await db[c.CONTACTS].update_one({"_id": contact["_id"]}, {"$set": {"is_active": False, "updated_at": utcnow()}})
    await audit.log(db, actor, "delete", "contact", contact["_id"], f"Deactivated contact {contact['name']}")
