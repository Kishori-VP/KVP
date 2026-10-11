"""Local-disk media storage with metadata in the media collection.

Files are de-duplicated per record by SHA-256, so the same photo uploaded twice
to the same event/visit/case returns the existing media document.
"""

import hashlib
import uuid
from pathlib import Path

from bson import ObjectId
from fastapi import HTTPException, UploadFile, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.db import collections as c
from app.utils.dates import utcnow

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "application/pdf": ".pdf",
}
ENTITY_COLLECTIONS = {
    "event": c.EVENTS,
    "home_visit": c.HOME_VISITS,
    "case": c.CASES,
    "girl": c.GIRLS,
    "activity_report": c.ACTIVITY_REPORTS,
}


async def save_upload(
    db: AsyncDatabase,
    file: UploadFile,
    entity_type: str,
    entity_id: ObjectId,
    user: dict,
    *,
    lat: float | None = None,
    lng: float | None = None,
    accuracy_m: float | None = None,
    captured_at=None,
    caption: str | None = None,
    sensitive: bool = False,
) -> tuple[dict, bool]:
    """Returns (media_doc, created)."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type {file.content_type}")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.max_upload_mb} MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty file")
    sha = hashlib.sha256(data).hexdigest()
    existing = await db[c.MEDIA].find_one({"sha256": sha, "entity_type": entity_type, "entity_id": entity_id})
    if existing:
        return existing, False

    now = utcnow()
    rel = Path(f"{now:%Y/%m}") / f"{uuid.uuid4().hex}{ALLOWED_TYPES[file.content_type]}"
    dest = settings.upload_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    doc = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "path": rel.as_posix(),
        "original_name": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(data),
        "sha256": sha,
        "caption": caption,
        "location": {"lat": lat, "lng": lng, "accuracy_m": accuracy_m} if lat is not None and lng is not None else None,
        "captured_at": captured_at,
        "location_flag": None if lat is not None else "missing_location",
        "sensitive": sensitive,
        "uploaded_by": user["_id"],
        "uploaded_at": now,
    }
    try:
        res = await db[c.MEDIA].insert_one(doc)
    except DuplicateKeyError:  # concurrent duplicate upload
        dest.unlink(missing_ok=True)
        return await db[c.MEDIA].find_one({"sha256": sha, "entity_type": entity_type, "entity_id": entity_id}), False
    doc["_id"] = res.inserted_id
    return doc, True


def file_path(doc: dict) -> Path:
    path = (settings.upload_dir / doc["path"]).resolve()
    if settings.upload_dir.resolve() not in path.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid media path")
    return path
