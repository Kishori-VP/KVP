from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.utils.dates import utcnow
from app.utils.mongo import serialize


async def log(
    db: AsyncDatabase,
    actor: dict | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    summary: str = "",
    changes: dict | None = None,
    meta: dict | None = None,
) -> None:
    """Record an audit entry.

    action: create | update | delete | approve | reject | reassign | revise |
            verify | login | import | config_change | status_change
    """
    await db[c.AUDIT_LOGS].insert_one(
        {
            "at": utcnow(),
            "actor_id": actor["_id"] if actor else None,
            "actor_name": actor.get("name") if actor else "system",
            "actor_role": actor.get("role") if actor else "system",
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": summary,
            "changes": serialize(changes) if changes else None,
            "meta": serialize(meta) if meta else None,
        }
    )
