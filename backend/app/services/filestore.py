"""Small GridFS helpers for files the app generates or receives (report files, template attachments).

Files are kept in MongoDB so they survive serverless hosts (Vercel), whose local disk is temporary
and not shared between instances. Entries saved before this used a ``path`` under a base folder;
those are still read from disk when present.
"""
from pathlib import Path

from bson import ObjectId
from fastapi import HTTPException, status
from gridfs import AsyncGridFSBucket
from gridfs.errors import NoFile
from pymongo.asynchronous.database import AsyncDatabase

REPORT_BUCKET = "report_files"


def _bucket(db: AsyncDatabase, bucket: str) -> AsyncGridFSBucket:
    return AsyncGridFSBucket(db, bucket_name=bucket)


async def put(db: AsyncDatabase, name: str, data: bytes, *, bucket: str = REPORT_BUCKET, **metadata) -> ObjectId:
    return await _bucket(db, bucket).upload_from_stream(name, data, metadata=metadata or None)


def _legacy_path(base: Path, rel: str) -> Path:
    path = (base / rel).resolve()
    if base.resolve() not in path.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file path")
    return path


async def get(db: AsyncDatabase, entry: dict, *, base: Path, bucket: str = REPORT_BUCKET) -> bytes | None:
    """The bytes of a stored entry (``gridfs_id`` or legacy ``path``), or None if missing."""
    if entry.get("gridfs_id"):
        try:
            stream = await _bucket(db, bucket).open_download_stream(entry["gridfs_id"])
            return await stream.read()
        except NoFile:
            return None
    if entry.get("path"):
        path = _legacy_path(base, entry["path"])
        return path.read_bytes() if path.exists() else None
    return None


async def delete(db: AsyncDatabase, entry: dict, *, base: Path, bucket: str = REPORT_BUCKET) -> None:
    if entry.get("gridfs_id"):
        try:
            await _bucket(db, bucket).delete(entry["gridfs_id"])
        except NoFile:
            pass
    elif entry.get("path"):
        _legacy_path(base, entry["path"]).unlink(missing_ok=True)
