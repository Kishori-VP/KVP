from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.services.app_settings import get_setting


async def next_sequence(db: AsyncDatabase, name: str) -> int:
    doc = await db[c.COUNTERS].find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return doc["seq"]


async def ensure_sequence_at_least(db: AsyncDatabase, name: str, value: int) -> None:
    await db[c.COUNTERS].update_one({"_id": name}, {"$max": {"seq": value}}, upsert=True)


async def next_girl_code(db: AsyncDatabase) -> tuple[str, int]:
    cfg = await get_setting(db, "girl_id")
    prefix, pad = cfg["prefix"], int(cfg.get("pad") or 0)
    seq = await next_sequence(db, f"girl:{prefix}")
    return f"{prefix}{str(seq).zfill(pad)}", seq


async def next_case_code(db: AsyncDatabase) -> str:
    seq = await next_sequence(db, "case")
    return f"CASE-{seq:05d}"
