"""Web Push (PWA) delivery for notifications.

Each in-app notification is also pushed to the user's subscribed devices when VAPID
keys are configured. Delivery is best-effort: failures never affect the in-app
notification, and expired subscriptions (404/410) are removed.
"""

import asyncio
import base64
import json
import logging

from bson import ObjectId
from cryptography.hazmat.primitives import serialization
from pymongo.asynchronous.database import AsyncDatabase
from pywebpush import WebPushException, webpush

from app.core.config import settings
from app.db import collections as c
from app.utils.dates import utcnow

log = logging.getLogger("kvp.push")
_background: set[asyncio.Task] = set()


def generate_vapid_keys() -> tuple[str, str]:
    """Returns (public_key, private_key) as base64url strings for the .env file."""
    from py_vapid import Vapid01

    v = Vapid01()
    v.generate_keys()
    raw_public = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    raw_private = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return b64(raw_public), b64(raw_private)


def _send(subscription: dict, payload: str) -> int | None:
    """Blocking send. Returns an HTTP status for a failed push, None on success."""
    try:
        webpush(
            subscription_info={"endpoint": subscription["endpoint"], "keys": subscription["keys"]},
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=24 * 3600,
        )
        return None
    except WebPushException as exc:
        return exc.response.status_code if exc.response is not None else 0


async def send_to_user(db: AsyncDatabase, user_id: ObjectId, payload: dict) -> int:
    if not settings.push_configured:
        return 0
    data = json.dumps(payload, default=str)
    sent = 0
    async for sub in db[c.PUSH_SUBSCRIPTIONS].find({"user_id": user_id}):
        status_code = await asyncio.to_thread(_send, sub, data)
        if status_code is None:
            sent += 1
            await db[c.PUSH_SUBSCRIPTIONS].update_one({"_id": sub["_id"]}, {"$set": {"last_success_at": utcnow()}})
        elif status_code in (404, 410):
            await db[c.PUSH_SUBSCRIPTIONS].delete_one({"_id": sub["_id"]})
        else:
            log.warning("Push to %s failed with status %s", sub["endpoint"][:60], status_code)
    return sent


def push_in_background(db: AsyncDatabase, user_id: ObjectId, payload: dict) -> None:
    """Fire-and-forget push so API responses are never slowed down by push services."""
    if not settings.push_configured:
        return
    task = asyncio.create_task(send_to_user(db, user_id, payload))
    _background.add(task)
    task.add_done_callback(_background.discard)
