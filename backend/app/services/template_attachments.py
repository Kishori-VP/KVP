"""PDF / Word files attached to a report template and included with every report it produces.

Files are stored in MongoDB GridFS (see app.services.filestore); the template keeps a list of entries:
{"id", "gridfs_id", "original_name", "content_type", "size_bytes", "uploaded_by", "uploaded_at"}.
Entries from before GridFS have a "path" under reports_dir instead.
"""

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.services import filestore
from app.utils.dates import utcnow

MAX_PER_TEMPLATE = 5
TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
FOLDER = "template_attachments"


def _ext(file: UploadFile) -> str:
    """Pick the extension from the declared type, falling back to the filename (browsers often send
    Word files as application/octet-stream)."""
    by_type = {mime: ext for ext, mime in TYPES.items()}
    ext = by_type.get(file.content_type or "") or Path(file.filename or "").suffix.lower()
    if ext not in TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Attach a PDF or Word (.doc, .docx) file")
    return ext


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", Path(name).name).strip() or "attachment"


async def save(db: AsyncDatabase, file: UploadFile, existing: list[dict], user: dict) -> dict:
    if len(existing) >= MAX_PER_TEMPLATE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A template can have at most {MAX_PER_TEMPLATE} attachments")
    ext = _ext(file)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.max_upload_mb} MB")
    att_id = uuid.uuid4().hex
    original = safe_name(file.filename or f"attachment{ext}")
    if not original.lower().endswith(ext):
        original += ext
    gridfs_id = await filestore.put(db, f"{FOLDER}/{att_id}{ext}", data, kind="template_attachment")
    return {"id": att_id, "gridfs_id": gridfs_id, "original_name": original, "content_type": TYPES[ext],
            "size_bytes": len(data), "uploaded_by": user["_id"], "uploaded_at": utcnow()}


async def read(db: AsyncDatabase, entry: dict) -> bytes | None:
    return await filestore.get(db, entry, base=settings.reports_dir)


async def remove(db: AsyncDatabase, entry: dict) -> None:
    await filestore.delete(db, entry, base=settings.reports_dir)


async def load_all(db: AsyncDatabase, tpl: dict | None) -> list[tuple[str, bytes, str]]:
    """(filename, content, content_type) for each attachment whose file still exists."""
    out = []
    for entry in (tpl or {}).get("attachments") or []:
        data = await read(db, entry)
        if data is not None:
            out.append((entry["original_name"], data, entry["content_type"]))
    return out
