from typing import Annotated

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.core.permissions import Role, full_matrix
from app.core.security import decode_access_token
from app.db import collections as c
from app.db.mongodb import get_database
from app.services.app_settings import get_setting

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/token")


def get_db() -> AsyncDatabase:
    return get_database()


Db = Annotated[AsyncDatabase, Depends(get_db)]


async def get_current_user(db: Db, token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise unauthorized
    sub = payload.get("sub")
    if not sub or not ObjectId.is_valid(sub):
        raise unauthorized
    user = await db[c.USERS].find_one({"_id": ObjectId(sub)})
    if user is None or not user.get("is_active", False):
        raise unauthorized
    return user


ADMIN_ROLES = (
    Role.SUPER_ADMIN.value,
    Role.ADMIN_1.value,
    Role.ADMIN_2.value,
    "super_admin",
    "admin_1",
    "admin_2",
    "admin",
    "stakeholder",
)
SUPER_ADMIN_ROLES = (
    Role.SUPER_ADMIN.value,
    "super_admin",
    "stakeholder",
)
ADMIN_1_ROLES = (
    Role.SUPER_ADMIN.value,
    Role.ADMIN_1.value,
    "super_admin",
    "admin_1",
)
OVERSIGHT_ROLES = SUPER_ADMIN_ROLES


def is_super_admin(user: dict) -> bool:
    return user.get("role") in SUPER_ADMIN_ROLES


def is_admin_1(user: dict) -> bool:
    return user.get("role") in (Role.ADMIN_1.value, "admin_1", "admin")


def is_admin_2(user: dict) -> bool:
    return user.get("role") in (Role.ADMIN_2.value, "admin_2")


def check_not_read_only(user: dict) -> None:
    """Admin-2 has read-only monitor access and cannot create, modify, or delete records."""
    if is_admin_2(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Admin-2 has read-only monitor access and cannot create or modify records",
        )


def check_can_delete(user: dict) -> None:
    """Only Super Admin can delete or remove records."""
    if not is_super_admin(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Super Admin has authority to delete or remove records",
        )


def check_can_add_volunteer(user: dict) -> None:
    """Only Super Admin can create volunteer accounts or users."""
    if not is_super_admin(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Super Admin has authority to create users or add volunteers",
        )


CurrentUser = Annotated[dict, Depends(get_current_user)]


async def require_stakeholder(user: CurrentUser) -> dict:
    """Allows Super Admin, Admin-1, and Admin-2."""
    if user.get("role") not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


Stakeholder = Annotated[dict, Depends(require_stakeholder)]
Admin = Stakeholder


async def require_super_admin(user: CurrentUser) -> dict:
    """Allows top-level oversight: Super Admin."""
    if not is_super_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super Admin access required")
    return user


SuperAdmin = Annotated[dict, Depends(require_super_admin)]


def user_village_ids(user: dict) -> list[ObjectId]:
    """Current villages of a volunteer. A volunteer can work in several villages."""
    ids = user.get("village_ids")
    if ids is None:  # records written before multi-village support
        ids = [user["village_id"]] if user.get("village_id") else []
    return [v if isinstance(v, ObjectId) else ObjectId(v) for v in ids]


def can_access_village(user: dict, village_id) -> bool:
    if user.get("role") in ADMIN_ROLES:
        return True
    if not village_id:
        return False
    vid = village_id if isinstance(village_id, ObjectId) else ObjectId(str(village_id))
    return vid in user_village_ids(user)


def require_permission(resource: str, action: str):
    async def checker(db: Db, user: CurrentUser) -> dict:
        if is_super_admin(user):
            return user
        if is_admin_2(user):
            if action != "read":
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"Admin-2 is read-only: cannot {action} {resource}")
            return user
        if is_admin_1(user):
            if action == "delete":
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"Admin-1 cannot delete {resource}")
            return user
        if user.get("role") in ADMIN_ROLES:
            return user
        perms = await get_setting(db, "permissions")
        matrix = full_matrix(perms.get("volunteer", {}))
        if action not in matrix[Role.VOLUNTEER].get(resource, []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not permitted: {action} {resource}")
        if not user_village_ids(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Volunteer has no assigned village")
        return user

    return checker


def village_scope(user: dict, field: str = "village_id") -> dict:
    """Mongo filter restricting Volunteers to their assigned villages. Admins & Stakeholders: no filter."""
    if user.get("role") in ADMIN_ROLES:
        return {}
    return {field: {"$in": user_village_ids(user)}}


def group_villages(group: dict) -> list[ObjectId]:
    """The villages whose girls may belong to a group: its own village plus any member villages."""
    return [group["village_id"], *group.get("member_village_ids", [])]


def group_scope(user: dict, village_id=None) -> dict:
    """Mongo filter for groups visible to the user, optionally narrowed to groups open to one village."""
    vids = None if user.get("role") in ADMIN_ROLES else user_village_ids(user)
    if village_id and can_access_village(user, village_id):
        vids = [ObjectId(str(village_id))]
    if vids is None:
        return {}
    return {"$or": [{"village_id": {"$in": vids}}, {"member_village_ids": {"$in": vids}}]}


def narrow_to_village(query: dict, user: dict, village_id, field: str = "village_id") -> None:
    """Apply an optional ?village_id= filter. Volunteers can narrow to one of their own villages;
    any other village is ignored, so they still only see their own villages."""
    if not village_id:
        return
    vid = ObjectId(str(village_id))
    if can_access_village(user, vid):
        query[field] = vid


def ensure_volunteer_village(user: dict, village_id) -> None:
    """Volunteers may only write records for one of their own villages."""
    if not can_access_village(user, village_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This village is not one of your assigned villages")


class PageParams(BaseModel):
    page: int
    page_size: int


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 25,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


Pagination = Annotated[PageParams, Depends(page_params)]
