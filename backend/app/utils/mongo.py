from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pydantic import AfterValidator
from pymongo.asynchronous.collection import AsyncCollection


def _validate_object_id(value: str) -> str:
    if not ObjectId.is_valid(value):
        raise ValueError(f"'{value}' is not a valid id")
    return value


# Use for incoming id fields in request bodies / query params.
ObjectIdStr = Annotated[str, AfterValidator(_validate_object_id)]


def oid(value: str | ObjectId | None) -> ObjectId | None:
    if value is None or isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid id: {value}")


def oids(values: list[str] | None) -> list[ObjectId]:
    return [oid(v) for v in values or []]


def serialize(value: Any) -> Any:
    """Recursively convert ObjectIds to strings and `_id` to `id`."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [serialize(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "_id":
                out["id"] = serialize(v)
            elif k in ("password_hash", "credentials_encrypted"):
                continue
            else:
                out[k] = serialize(v)
        return out
    return value


async def get_or_404(coll: AsyncCollection, id_: str | ObjectId, label: str, extra: dict | None = None) -> dict:
    query = {"_id": oid(id_), **(extra or {})}
    doc = await coll.find_one(query)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return doc


async def paginate(
    coll: AsyncCollection,
    query: dict,
    page: int,
    page_size: int,
    sort: list[tuple[str, int]] | None = None,
    projection: dict | None = None,
) -> dict:
    total = await coll.count_documents(query)
    cursor = coll.find(query, projection).skip((page - 1) * page_size).limit(page_size)
    if sort:
        cursor = cursor.sort(sort)
    items = [serialize(d) async for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def diff(before: dict, after: dict, fields: list[str] | None = None) -> dict:
    """Field-level changes between two documents, for audit trails."""
    keys = fields or sorted(set(before) | set(after))
    changes = {}
    for k in keys:
        if k in ("_id", "updated_at", "password_hash", "credentials_encrypted"):
            continue
        if before.get(k) != after.get(k):
            changes[k] = {"from": serialize(before.get(k)), "to": serialize(after.get(k))}
    return changes
