"""Image & media management (PRD 4.12) for visits, cases, girls and reports."""

from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.core.deps import ADMIN_ROLES, CurrentUser, Db, Pagination, Stakeholder, require_permission, village_scope
from app.core.permissions import Role
from app.db import collections as c
from app.services import audit, storage
from app.services.events import local_day_bounds
from app.utils.mongo import ObjectIdStr, get_or_404, oid, serialize

router = APIRouter(prefix="/media", tags=["media"])
EntityType = Literal["event", "home_visit", "case", "girl", "activity_report"]
# Identity documents attached to a girl; each girl holds at most one file per kind.
MediaKind = Literal["aadhaar_front", "aadhaar_back"]
PERMISSION_RESOURCE = {"event": "events", "home_visit": "home_visits", "case": "cases", "girl": "girls",
                       "activity_report": "activity_reports"}


async def _can_access(db, user: dict, media: dict) -> None:
    if user["role"] in ADMIN_ROLES:
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
    kind: MediaKind | None = Form(None),
):
    if kind and entity_type != "girl":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Document kinds apply only to girls")
    if kind and not (file.content_type or "").startswith("image/") and file.content_type != "application/pdf":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Aadhaar card must be an image or PDF")
    await require_permission(PERMISSION_RESOURCE[entity_type], "update")(db, user)
    coll = storage.ENTITY_COLLECTIONS[entity_type]
    record = await get_or_404(db[coll], entity_id, entity_type.replace("_", " ").title(), village_scope(user))
    if entity_type == "event" and record.get("status") == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is cancelled")
    doc, created = await storage.save_upload(
        db, file, entity_type, record["_id"], user, lat=lat, lng=lng, accuracy_m=accuracy_m,
        captured_at=captured_at, caption=caption, sensitive=sensitive or entity_type in ("case", "girl"),
    )
    if kind:
        if doc.get("kind") not in (None, kind):
            raise HTTPException(status.HTTP_409_CONFLICT, f"This file is already uploaded as {doc['kind'].replace('_', ' ')}")
        await _replace_kind(db, user, doc, kind)
        doc["kind"] = kind
    if created:
        if entity_type in ("event", "home_visit"):
            await db[coll].update_one({"_id": record["_id"]}, {"$addToSet": {"media_ids": doc["_id"]}})
        await audit.log(db, user, "create", "media", doc["_id"], f"Uploaded media to {entity_type}")
    return {**serialize(doc), "duplicate": not created}


async def _replace_kind(db, user: dict, doc: dict, kind: str) -> None:
    """Tag `doc` with `kind` and remove the girl's previous file of that kind."""
    old = await db[c.MEDIA].find_one(
        {"entity_type": doc["entity_type"], "entity_id": doc["entity_id"], "kind": kind, "_id": {"$ne": doc["_id"]}})
    await db[c.MEDIA].update_one({"_id": doc["_id"]}, {"$set": {"kind": kind}})
    if old:
        await db[c.MEDIA].delete_one({"_id": old["_id"]})
        await storage.delete_file(db, old)
        await audit.log(db, user, "delete", "media", old["_id"], f"Replaced {kind.replace('_', ' ')}")


@router.get("")
async def list_media(db: Db, user: CurrentUser, entity_type: EntityType = Query(...), entity_id: ObjectIdStr = Query(...)):
    await require_permission(PERMISSION_RESOURCE[entity_type], "read")(db, user)
    coll = storage.ENTITY_COLLECTIONS[entity_type]
    await get_or_404(db[coll], entity_id, entity_type, village_scope(user))
    query: dict = {"entity_type": entity_type, "entity_id": oid(entity_id)}
    if user["role"] == Role.VOLUNTEER:
        query["sensitive"] = False
    return serialize(await db[c.MEDIA].find(query).sort("uploaded_at", -1).to_list())


LIBRARY_ROLES = (Role.SUPER_ADMIN.value, Role.ADMIN_1.value)
LIBRARY_LABEL_FIELDS = {"event": "title", "case": "title", "girl": "name"}


@router.get("/library")
async def media_library(
    db: Db,
    user: CurrentUser,
    pg: Pagination,
    village_id: ObjectIdStr | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Every uploaded photo and file across the programme, newest first, filterable by village
    and upload date. Super Admin and Admin-1 only. Media has no village of its own, so the
    village comes from the record it is attached to (event, home visit, case, girl, report)."""
    if user["role"] not in LIBRARY_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The media library is for Super Admin and Admin-1")
    query: dict = {}
    if start_date or end_date:
        s, e = local_day_bounds(start_date or date(2000, 1, 1), end_date or date(2100, 1, 1))
        query["uploaded_at"] = {"$gte": s, "$lt": e}
    if village_id:
        owners = []
        for etype, coll in storage.ENTITY_COLLECTIONS.items():
            ids = await db[coll].distinct("_id", {"village_id": oid(village_id)})
            if ids:
                owners.append({"entity_type": etype, "entity_id": {"$in": ids}})
        if not owners:
            return {"items": [], "total": 0, "page": pg.page, "page_size": pg.page_size}
        query["$or"] = owners
    total = await db[c.MEDIA].count_documents(query)
    docs = await db[c.MEDIA].find(query).sort([("uploaded_at", -1), ("_id", -1)]) \
        .skip((pg.page - 1) * pg.page_size).limit(pg.page_size).to_list()

    # Village and a readable label for each file, from the record it belongs to.
    parents: dict = {}
    for etype, coll in storage.ENTITY_COLLECTIONS.items():
        ids = [d["entity_id"] for d in docs if d["entity_type"] == etype]
        if ids:
            fields = {"village_id": 1, LIBRARY_LABEL_FIELDS.get(etype, "village_id"): 1}
            async for p in db[coll].find({"_id": {"$in": ids}}, fields):
                parents[(etype, p["_id"])] = p
    village_ids = {p.get("village_id") for p in parents.values()} - {None}
    villages = {v["_id"]: v for v in await db[c.VILLAGES].find({"_id": {"$in": list(village_ids)}},
                                                                {"name": 1, "name_mr": 1}).to_list()}
    uploaders = {u["_id"]: u.get("name") for u in await db[c.USERS].find(
        {"_id": {"$in": list({d.get("uploaded_by") for d in docs} - {None})}}, {"name": 1}).to_list()}
    items = []
    for d in docs:
        parent = parents.get((d["entity_type"], d["entity_id"])) or {}
        village = villages.get(parent.get("village_id")) or {}
        items.append({
            **serialize(d),
            "village_id": str(parent["village_id"]) if parent.get("village_id") else None,
            "village_name": village.get("name"),
            "village_name_mr": village.get("name_mr"),
            "entity_label": parent.get(LIBRARY_LABEL_FIELDS.get(d["entity_type"], "")),
            "uploaded_by_name": uploaders.get(d.get("uploaded_by")),
        })
    return {"items": items, "total": total, "page": pg.page, "page_size": pg.page_size}


@router.get("/{media_id}")
async def get_media(media_id: str, db: Db, user: CurrentUser):
    media = await get_or_404(db[c.MEDIA], media_id, "Media")
    await _can_access(db, user, media)
    return serialize(media)


@router.get("/{media_id}/file")
async def download(media_id: str, db: Db, user: CurrentUser):
    media = await get_or_404(db[c.MEDIA], media_id, "Media")
    await _can_access(db, user, media)
    data = await storage.read_file(db, media)
    if data is None:
        raise HTTPException(status.HTTP_410_GONE, "File is missing from storage")
    name = media.get("original_name") or f"media-{media['_id']}"
    return Response(data, media_type=media["content_type"], headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}", "Cache-Control": "private, max-age=86400"})


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(media_id: str, db: Db, actor: Stakeholder, reason: Annotated[str, Query(min_length=3)]):
    from app.core.deps import check_can_delete
    check_can_delete(actor)
    media = await get_or_404(db[c.MEDIA], media_id, "Media")
    coll = storage.ENTITY_COLLECTIONS.get(media["entity_type"])
    if coll:
        await db[coll].update_one({"_id": media["entity_id"]}, {"$pull": {"media_ids": media["_id"]}})
    await db[c.MEDIA].delete_one({"_id": media["_id"]})
    await storage.delete_file(db, media)
    await audit.log(db, actor, "delete", "media", media["_id"], f"Deleted media from {media['entity_type']}",
                    meta={"reason": reason, "original_name": media.get("original_name")})
