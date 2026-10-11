"""Image & media management (PRD 4.12) for visits, cases, girls and reports."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser, Db, Stakeholder, require_permission, village_scope
from app.core.permissions import Role
from app.db import collections as c
from app.services import audit, storage
from app.utils.mongo import ObjectIdStr, get_or_404, oid, serialize

router = APIRouter(prefix="/media", tags=["media"])
EntityType = Literal["event", "home_visit", "case", "girl", "activity_report"]
PERMISSION_RESOURCE = {"event": "events", "home_visit": "home_visits", "case": "cases", "girl": "girls",
                       "activity_report": "activity_reports"}


async def _can_access(db, user: dict, media: dict) -> None:
    if user["role"] == Role.STAKEHOLDER:
        return
    if media.get("sensitive"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sensitive media is restricted")
    coll = storage.ENTITY_COLLECTIONS[media["entity_type"]]
    if not await db[coll].find_one({"_id": media["entity_id"], **village_scope(user)}, {"_id": 1}):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    db: Db,
    user: CurrentUser,
    entity_type: EntityType = Form(...),
    entity_id: ObjectIdStr = Form(...),
    file: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    accuracy_m: float | None = Form(None),
    captured_at: datetime | None = Form(None),
    caption: str | None = Form(None),
    sensitive: bool = Form(False),
):
    await require_permission(PERMISSION_RESOURCE[entity_type], "update")(db, user)
    coll = storage.ENTITY_COLLECTIONS[entity_type]
    record = await get_or_404(db[coll], entity_id, entity_type.replace("_", " ").title(), village_scope(user))
    doc, created = await storage.save_upload(
        db, file, entity_type, record["_id"], user, lat=lat, lng=lng, accuracy_m=accuracy_m,
        captured_at=captured_at, caption=caption, sensitive=sensitive or entity_type in ("case", "girl"),
    )
    if created:
        if entity_type in ("event", "home_visit"):
            await db[coll].update_one({"_id": record["_id"]}, {"$addToSet": {"media_ids": doc["_id"]}})
        await audit.log(db, user, "create", "media", doc["_id"], f"Uploaded media to {entity_type}")
    return {**serialize(doc), "duplicate": not created}


@router.get("")
async def list_media(db: Db, user: CurrentUser, entity_type: EntityType = Query(...), entity_id: ObjectIdStr = Query(...)):
    await require_permission(PERMISSION_RESOURCE[entity_type], "read")(db, user)
    coll = storage.ENTITY_COLLECTIONS[entity_type]
    await get_or_404(db[coll], entity_id, entity_type, village_scope(user))
    query: dict = {"entity_type": entity_type, "entity_id": oid(entity_id)}
    if user["role"] == Role.VOLUNTEER:
        query["sensitive"] = False
    return serialize(await db[c.MEDIA].find(query).sort("uploaded_at", -1).to_list())


@router.get("/{media_id}")
async def get_media(media_id: str, db: Db, user: CurrentUser):
    media = await get_or_404(db[c.MEDIA], media_id, "Media")
    await _can_access(db, user, media)
    return serialize(media)


@router.get("/{media_id}/file")
async def download(media_id: str, db: Db, user: CurrentUser):
    media = await get_or_404(db[c.MEDIA], media_id, "Media")
    await _can_access(db, user, media)
    path = storage.file_path(media)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "File is missing from storage")
    return FileResponse(path, media_type=media["content_type"], filename=media.get("original_name") or path.name)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(media_id: str, db: Db, actor: Stakeholder, reason: Annotated[str, Query(min_length=3)]):
    media = await get_or_404(db[c.MEDIA], media_id, "Media")
    coll = storage.ENTITY_COLLECTIONS.get(media["entity_type"])
    if coll:
        await db[coll].update_one({"_id": media["entity_id"]}, {"$pull": {"media_ids": media["_id"]}})
    await db[c.MEDIA].delete_one({"_id": media["_id"]})
    storage.file_path(media).unlink(missing_ok=True)
    await audit.log(db, actor, "delete", "media", media["_id"], f"Deleted media from {media['entity_type']}",
                    meta={"reason": reason, "original_name": media.get("original_name")})
