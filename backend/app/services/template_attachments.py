"""PDF / Word files attached to a report template and included with every report it produces.

Files live under reports_dir/template_attachments; the template keeps a list of entries:
{"id", "path", "original_name", "content_type", "size_bytes", "uploaded_by", "uploaded_at"}.
"""

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
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


async def save(file: UploadFile, existing: list[dict], user: dict) -> dict:
    if len(existing) >= MAX_PER_TEMPLATE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A template can have at most {MAX_PER_TEMPLATE} attachments")
    ext = _ext(file)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.max_upload_mb} MB")
    att_id = uuid.uuid4().hex
    rel = Path(FOLDER) / f"{att_id}{ext}"
    dest = settings.reports_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    original = safe_name(file.filename or f"attachment{ext}")
    if not original.lower().endswith(ext):
        original += ext
    return {"id": att_id, "path": rel.as_posix(), "original_name": original, "content_type": TYPES[ext],
            "size_bytes": len(data), "uploaded_by": user["_id"], "uploaded_at": utcnow()}


def file_path(entry: dict) -> Path:
    path = (settings.reports_dir / entry["path"]).resolve()
    if settings.reports_dir.resolve() not in path.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid attachment path")
    return path


def load_all(tpl: dict | None) -> list[tuple[str, bytes, str]]:
    """(filename, content, content_type) for each attachment still on disk."""
    out = []
    for entry in (tpl or {}).get("attachments") or []:
        path = file_path(entry)
        if path.exists():
            out.append((entry["original_name"], path.read_bytes(), entry["content_type"]))
    return out
