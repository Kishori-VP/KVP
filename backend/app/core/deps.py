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


CurrentUser = Annotated[dict, Depends(get_current_user)]


async def require_stakeholder(user: CurrentUser) -> dict:
    if user["role"] != Role.STAKEHOLDER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Stakeholder access required")
    return user


Stakeholder = Annotated[dict, Depends(require_stakeholder)]


def require_permission(resource: str, action: str):
    async def checker(db: Db, user: CurrentUser) -> dict:
        if user["role"] == Role.STAKEHOLDER:
            return user
        perms = await get_setting(db, "permissions")
        matrix = full_matrix(perms.get("volunteer", {}))
        if action not in matrix[Role.VOLUNTEER].get(resource, []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not permitted: {action} {resource}")
        if not user_village_ids(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Volunteer has no assigned village")
        return user

    return checker


def user_village_ids(user: dict) -> list:
    """Current villages of a volunteer. A volunteer can work in several villages."""
    ids = user.get("village_ids")
    if ids is None:  # records written before multi-village support
        ids = [user["village_id"]] if user.get("village_id") else []
    return list(ids)


def village_scope(user: dict, field: str = "village_id") -> dict:
    """Mongo filter restricting Volunteers to their assigned villages. Stakeholders: no filter."""
    if user["role"] == Role.STAKEHOLDER:
        return {}
    return {field: {"$in": user_village_ids(user)}}


def narrow_to_village(query: dict, user: dict, village_id, field: str = "village_id") -> None:
    """Apply an optional ?village_id= filter. Volunteers can narrow to one of their own villages;
    any other village is ignored, so they still only see their own villages."""
    if not village_id:
        return
    vid = ObjectId(str(village_id))
    if user["role"] == Role.STAKEHOLDER or vid in user_village_ids(user):
        query[field] = vid


def ensure_volunteer_village(user: dict, village_id) -> None:
    """Volunteers may only write records for one of their own villages."""
    if user["role"] == Role.VOLUNTEER and village_id not in user_village_ids(user):
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
