"""Media storage: file bytes in MongoDB GridFS, metadata in the media collection.

GridFS keeps photos with the rest of the data, so they survive on serverless hosts (Vercel),
where the local disk is temporary and not shared between instances. Older records saved to the
local upload folder (``path`` instead of ``gridfs_id``) are still read from disk.

Files are de-duplicated per record by SHA-256, so the same photo uploaded twice
to the same event/visit/case returns the existing media document.
"""

import hashlib
import uuid
from pathlib import Path

from bson import ObjectId
from fastapi import HTTPException, UploadFile, status
from gridfs import AsyncGridFSBucket
from gridfs.errors import NoFile
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.db import collections as c
from app.utils.dates import utcnow

BUCKET = "media_files"
# Some phones and browsers report these names for the same formats.
TYPE_ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg", "image/heif": "image/heic", "image/x-png": "image/png"}
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
    content_type = TYPE_ALIASES.get(file.content_type or "", file.content_type or "")
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"Unsupported file type {file.content_type or 'unknown'}. Use a JPG, PNG or WEBP photo, a PDF, or an MP4 video.")
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
    name = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    gridfs_id = await _bucket(db).upload_from_stream(
        name, data, metadata={"content_type": content_type, "entity_type": entity_type, "entity_id": entity_id})

    doc = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "gridfs_id": gridfs_id,
        "original_name": file.filename,
        "content_type": content_type,
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
        await delete_file(db, {"gridfs_id": gridfs_id})
        return await db[c.MEDIA].find_one({"sha256": sha, "entity_type": entity_type, "entity_id": entity_id}), False
    doc["_id"] = res.inserted_id
    return doc, True


def _bucket(db: AsyncDatabase) -> AsyncGridFSBucket:
    return AsyncGridFSBucket(db, bucket_name=BUCKET)


def file_path(doc: dict) -> Path:
    """Disk location of a media file saved before GridFS storage (``path`` field)."""
    path = (settings.upload_dir / doc["path"]).resolve()
    if settings.upload_dir.resolve() not in path.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid media path")
    return path


async def read_file(db: AsyncDatabase, doc: dict) -> bytes | None:
    """The file's bytes, or None if it is missing (e.g. an old upload lost from temporary disk)."""
    if doc.get("gridfs_id"):
        try:
            stream = await _bucket(db).open_download_stream(doc["gridfs_id"])
            return await stream.read()
        except NoFile:
            return None
    if doc.get("path"):
        path = file_path(doc)
        return path.read_bytes() if path.exists() else None
    return None


async def delete_file(db: AsyncDatabase, doc: dict) -> None:
    if doc.get("gridfs_id"):
        try:
            await _bucket(db).delete(doc["gridfs_id"])
        except NoFile:
            pass
    elif doc.get("path"):
        file_path(doc).unlink(missing_ok=True)
