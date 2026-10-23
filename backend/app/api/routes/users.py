import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.deps import Db, Pagination, Stakeholder, user_village_ids
from app.core.permissions import Role
from app.core.security import hash_password
from app.db import collections as c
from app.schemas.users import PasswordReset, RoleChange, StatusChange, UserCreate, UserUpdate
from app.services import assignments, audit
from app.utils.dates import utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, paginate, serialize

router = APIRouter(prefix="/users", tags=["users"])


def _duplicate_error(exc: DuplicateKeyError) -> HTTPException:
    field = "email" if "email" in str(exc) else "phone"
    return HTTPException(status.HTTP_409_CONFLICT, f"A user with this {field} already exists")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: Db, actor: Stakeholder):
    now = utcnow()
    doc = {
        "name": body.name.strip(),
        "email": body.email.lower() if body.email else None,
        "phone": body.phone,
        "password_hash": hash_password(body.password),
        "role": body.role.value,
        "village_id": None,
        "village_ids": [],
        "taluka_id": None,
        "group_ids": [],
        "designation": body.designation,
        "contact": body.contact.model_dump(),
        "is_active": body.is_active,
        "created_by": actor["_id"],
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    from app.core.deps import OVERSIGHT_ROLES
    if body.role in (Role.STAKEHOLDER, Role.SUPER_ADMIN) and actor.get("role") not in OVERSIGHT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Stakeholder can create another Stakeholder")

    if body.role == Role.VOLUNTEER and body.village_ids:
        # Validate before inserting so a bad village/group never leaves an orphan user.
        villages = [await assignments.load_active_village(db, vid) for vid in body.village_ids]
        await assignments.validate_groups(db, [v["_id"] for v in villages], body.group_ids)
    try:
        res = await db[c.USERS].insert_one(doc)
    except DuplicateKeyError as exc:
        raise _duplicate_error(exc)
    doc["_id"] = res.inserted_id

    if body.role == Role.VOLUNTEER and body.village_ids:
        group_village = {g["_id"]: g["village_id"] async for g in db[c.GROUPS].find(
            {"_id": {"$in": [oid(g) for g in body.group_ids]}}, {"village_id": 1})}
        for vid in body.village_ids:
            await assignments.assign_village(
                db, doc, vid, [g for g in body.group_ids if group_village.get(oid(g)) == oid(vid)], actor,
                "Initial assignment", body.assignment_start_date,
            )
    await audit.log(db, actor, "create", "user", doc["_id"], f"Created {body.role.value} {doc['name']}")
    return serialize(await db[c.USERS].find_one({"_id": doc["_id"]}))


@router.get("")
async def list_users(
    db: Db,
    _: Stakeholder,
    pg: Pagination,
    role: Role | None = None,
    village_id: ObjectIdStr | None = None,
    taluka_id: ObjectIdStr | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(description="Search name, phone or email")] = None,
):
    query: dict = {}
    if role:
        query["role"] = role.value
    if village_id:
        query["village_ids"] = oid(village_id)
    if taluka_id:
        taluka_villages = await db[c.VILLAGES].distinct("_id", {"taluka_id": oid(taluka_id)})
        query.setdefault("village_ids", {"$in": taluka_villages})
    if is_active is not None:
        query["is_active"] = is_active
    if q:
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"name": rx}, {"phone": rx}, {"email": rx}]
    return await paginate(db[c.USERS], query, pg.page, pg.page_size, sort=[("name", 1)])


@router.get("/{user_id}")
async def get_user(user_id: str, db: Db, _: Stakeholder):
    user = await get_or_404(db[c.USERS], user_id, "User")
    out = serialize(user)
    if user.get("village_id"):
        out["village"] = serialize(await db[c.VILLAGES].find_one({"_id": user["village_id"]}))
        out["villages"] = serialize(await db[c.VILLAGES].find({"_id": {"$in": user_village_ids(user)}}).sort("name", 1).to_list())
        out["groups"] = serialize(await db[c.GROUPS].find({"_id": {"$in": user.get("group_ids", [])}}).to_list())
    out["assignment_history"] = serialize(
        await db[c.VOLUNTEER_ASSIGNMENTS].find({"volunteer_id": user["_id"]}).sort([("start_date", -1), ("created_at", -1)]).to_list()
    )
    return out


@router.patch("/{user_id}")
async def update_user(user_id: str, body: UserUpdate, db: Db, actor: Stakeholder):
    before = await get_or_404(db[c.USERS], user_id, "User")
    updates = body.model_dump(exclude_unset=True)
    if "email" in updates and updates["email"]:
        updates["email"] = updates["email"].lower()
    if not updates:
        return serialize(before)
    updates["updated_at"] = utcnow()
    try:
        await db[c.USERS].update_one({"_id": before["_id"]}, {"$set": updates})
    except DuplicateKeyError as exc:
        raise _duplicate_error(exc)
    after = await db[c.USERS].find_one({"_id": before["_id"]})
    await audit.log(db, actor, "update", "user", before["_id"], f"Updated {after['name']}", diff(before, after))
    return serialize(after)


@router.patch("/{user_id}/role")
async def change_role(user_id: str, body: RoleChange, db: Db, actor: Stakeholder):
    user = await get_or_404(db[c.USERS], user_id, "User")
    if user["role"] == body.role:
        raise HTTPException(status.HTTP_409_CONFLICT, f"User is already a {body.role.value}")
    # SEDT rule: an administrative Stakeholder account must not be converted into a field Volunteer.
    from app.core.deps import OVERSIGHT_ROLES
    if user.get("role") in OVERSIGHT_ROLES and actor.get("role") not in OVERSIGHT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Stakeholder can modify a Stakeholder account")
    if body.role in (Role.STAKEHOLDER, Role.SUPER_ADMIN) and actor.get("role") not in OVERSIGHT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Stakeholder can promote a user to Stakeholder")
    if user["role"] in (Role.STAKEHOLDER, Role.SUPER_ADMIN, Role.ADMIN) and body.role == Role.VOLUNTEER and actor.get("role") not in OVERSIGHT_ROLES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Stakeholder/Admin accounts cannot be converted to Volunteers. Create a separate Volunteer account.")
    if user["_id"] == actor["_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")
    reason = body.reason or "Role change"
    if body.role == Role.VOLUNTEER:
        await db[c.USERS].update_one({"_id": user["_id"]}, {"$set": {"role": Role.VOLUNTEER.value}})
        if body.village_id:
            await assignments.assign_village(db, user, body.village_id, [], actor, reason)
    else:
        await assignments.end_assignment(db, user, actor, reason)
        await db[c.USERS].update_one({"_id": user["_id"]}, {"$set": {"role": body.role.value}})
    await audit.log(
        db, actor, "update", "user", user["_id"], f"Role changed to {body.role.value}",
        {"role": {"from": user["role"], "to": body.role.value}},
    )
    return serialize(await db[c.USERS].find_one({"_id": user["_id"]}))


@router.patch("/{user_id}/status")
async def change_status(user_id: str, body: StatusChange, db: Db, actor: Stakeholder):
    user = await get_or_404(db[c.USERS], user_id, "User")
    if user["_id"] == actor["_id"] and not body.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    await db[c.USERS].update_one({"_id": user["_id"]}, {"$set": {"is_active": body.is_active, "updated_at": utcnow()}})
    await audit.log(
        db, actor, "status_change", "user", user["_id"],
        f"{'Activated' if body.is_active else 'Deactivated'} {user['name']}",
        {"is_active": {"from": user["is_active"], "to": body.is_active}}, {"reason": body.reason},
    )
    return serialize(await db[c.USERS].find_one({"_id": user["_id"]}))


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: str, body: PasswordReset, db: Db, actor: Stakeholder):
    user = await get_or_404(db[c.USERS], user_id, "User")
    await db[c.USERS].update_one(
        {"_id": user["_id"]}, {"$set": {"password_hash": hash_password(body.new_password), "updated_at": utcnow()}}
    )
    await audit.log(db, actor, "update", "user", user["_id"], f"Reset password for {user['name']}")
