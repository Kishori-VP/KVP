"""In-app notifications, also delivered by Web Push to subscribed devices when configured."""

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.permissions import Role
from app.db import collections as c
from app.services import push
from app.utils.dates import utcnow


async def notify(
    db: AsyncDatabase,
    user_id: ObjectId,
    type_: str,
    title: str,
    message: str = "",
    *,
    entity_type: str | None = None,
    entity_id: ObjectId | None = None,
    severity: str = "info",
    dedupe_key: str | None = None,
) -> bool:
    """Create a notification. With a dedupe_key, the same alert is only created once.

    Returns True if a new notification was created.
    """
    doc = {
        "user_id": user_id,
        "type": type_,
        "title": title,
        "message": message,
        "severity": severity,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "is_read": False,
        "read_at": None,
        "created_at": utcnow(),
    }
    if dedupe_key:
        doc["dedupe_key"] = f"{user_id}:{dedupe_key}"
    try:
        res = await db[c.NOTIFICATIONS].insert_one(doc)
    except DuplicateKeyError:
        return False
    push.push_in_background(db, user_id, {
        "id": str(res.inserted_id), "type": type_, "title": title, "body": message, "severity": severity,
        "entity_type": entity_type, "entity_id": str(entity_id) if entity_id else None,
    })
    return True


async def notify_stakeholders(db: AsyncDatabase, type_: str, title: str, message: str = "", *,
                              exclude: ObjectId | None = None, **kwargs) -> int:
    created = 0
    async for u in db[c.USERS].find({"role": Role.STAKEHOLDER.value, "is_active": True}, {"_id": 1}):
        if u["_id"] != exclude and await notify(db, u["_id"], type_, title, message, **kwargs):
            created += 1
    return created
