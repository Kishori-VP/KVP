from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import CurrentUser, Db
from app.core.security import create_access_token, hash_password, verify_password
from app.db import collections as c
from app.schemas.users import ChangePasswordRequest, LoginRequest, TokenResponse
from app.services import audit
from app.utils.dates import utcnow
from app.utils.mongo import serialize

router = APIRouter(prefix="/auth", tags=["auth"])


async def _authenticate(db, identifier: str, password: str, request: Request) -> TokenResponse:
    identifier = identifier.strip()
    query = {"email": identifier.lower()} if "@" in identifier else {"phone": identifier}
    user = await db[c.USERS].find_one(query)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect credentials")
    if not user.get("is_active"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive")
    await db[c.USERS].update_one({"_id": user["_id"]}, {"$set": {"last_login_at": utcnow()}})
    await audit.log(db, user, "login", "user", user["_id"], meta={"ip": request.client.host if request.client else None})
    token, expires_in = create_access_token(str(user["_id"]), user["role"])
    return TokenResponse(access_token=token, expires_in=expires_in, user=serialize(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: Db, request: Request):
    """Log in with email or mobile number."""
    return await _authenticate(db, body.identifier, body.password, request)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
async def login_form(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db, request: Request):
    """OAuth2 form login, used by the Swagger 'Authorize' button."""
    return await _authenticate(db, form.username, form.password, request)


@router.get("/me")
async def me(user: CurrentUser, db: Db):
    out = serialize(user)
    if user.get("village_id"):
        village = await db[c.VILLAGES].find_one({"_id": user["village_id"]}, {"name": 1, "name_mr": 1})
        out["village"] = serialize(village)
    return out


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, user: CurrentUser, db: Db):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    await db[c.USERS].update_one(
        {"_id": user["_id"]}, {"$set": {"password_hash": hash_password(body.new_password), "updated_at": utcnow()}}
    )
    await audit.log(db, user, "update", "user", user["_id"], "Changed own password")
