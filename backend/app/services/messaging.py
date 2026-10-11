"""SMS delivery to people who are not app users (girls / families), via an outbox.

Provider is the active default `sms` provider under /config/providers:
- console  : records messages in the outbox without sending (development / dry runs)
- twilio   : config {"from": "+1..."}; credentials {"account_sid", "auth_token"}
- fast2sms : config {"route": "q"};    credentials {"api_key"}   (Indian bulk SMS)

Every message is stored in message_outbox with its delivery status, so Stakeholders
can audit what was sent to beneficiaries.
"""

import re

import httpx
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core import crypto
from app.db import collections as c
from app.utils.dates import utcnow

SUPPORTED_PROVIDERS = ("console", "twilio", "fast2sms")


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


async def active_provider(db: AsyncDatabase) -> dict | None:
    return await db[c.PROVIDER_CONFIGS].find_one(
        {"provider_type": "sms", "is_active": True}, sort=[("is_default", -1), ("updated_at", -1)])


def _secret(provider: dict, key: str) -> str | None:
    token = (provider.get("credentials_encrypted") or {}).get(key)
    return crypto.decrypt(token) if token else None


async def _deliver(provider: dict, phone: str, body: str) -> tuple[str, str | None]:
    """Returns (status, error)."""
    name = provider["provider_name"]
    cfg = provider.get("config") or {}
    async with httpx.AsyncClient(timeout=20) as client:
        if name == "twilio":
            sid, token = _secret(provider, "account_sid"), _secret(provider, "auth_token")
            if not (sid and token and cfg.get("from")):
                return "failed", "Twilio needs credentials account_sid, auth_token and config.from"
            r = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                                  auth=(sid, token), data={"To": f"+91{phone}", "From": cfg["from"], "Body": body})
        elif name == "fast2sms":
            key = _secret(provider, "api_key")
            if not key:
                return "failed", "Fast2SMS needs credentials.api_key"
            r = await client.post("https://www.fast2sms.com/dev/bulkV2", headers={"authorization": key},
                                  json={"route": cfg.get("route", "q"), "message": body, "numbers": phone,
                                        "language": "unicode"})
        else:
            return "failed", f"Unsupported SMS provider '{name}'"
    if r.status_code >= 400:
        return "failed", f"HTTP {r.status_code}: {r.text[:200]}"
    return "sent", None


async def send_sms(
    db: AsyncDatabase,
    phone: str | None,
    body: str,
    *,
    purpose: str,
    entity_type: str | None = None,
    entity_id=None,
    recipient_name: str | None = None,
    dedupe_key: str | None = None,
    created_by=None,
) -> dict | None:
    """Queue and send one SMS. Returns the outbox doc, or None if it was a duplicate."""
    number = normalize_phone(phone)
    provider = await active_provider(db)
    doc = {
        "channel": "sms",
        "to": number,
        "recipient_name": recipient_name,
        "body": body,
        "purpose": purpose,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "provider": provider["provider_name"] if provider else None,
        "status": "queued",
        "error": None,
        "created_by": created_by,
        "created_at": utcnow(),
        "sent_at": None,
    }
    if not number:
        doc.update(status="skipped", error="No valid mobile number")
    elif not provider:
        doc.update(status="skipped", error="No active SMS provider configured")
    elif dedupe_key:
        # Only real send attempts reserve the dedupe key, so skipped messages can be retried later.
        doc["dedupe_key"] = dedupe_key
    try:
        res = await db[c.MESSAGE_OUTBOX].insert_one(doc)
    except DuplicateKeyError:
        return None
    doc["_id"] = res.inserted_id
    if doc["status"] != "queued":
        return doc

    if provider["provider_name"] == "console":
        status_, error = "logged", None
    else:
        try:
            status_, error = await _deliver(provider, number, body)
        except (httpx.HTTPError, crypto.CredentialsKeyMissing) as exc:
            status_, error = "failed", str(exc)[:300]
    doc.update(status=status_, error=error, sent_at=utcnow() if status_ in ("sent", "logged") else None)
    update: dict = {"$set": {"status": status_, "error": error, "sent_at": doc["sent_at"]}}
    if status_ == "failed":
        update["$unset"] = {"dedupe_key": ""}  # allow a retry on the next run
    await db[c.MESSAGE_OUTBOX].update_one({"_id": res.inserted_id}, update)
    return doc
