from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c


async def next_sequence(db: AsyncDatabase, name: str) -> int:
    doc = await db[c.COUNTERS].find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return doc["seq"]


async def ensure_sequence_at_least(db: AsyncDatabase, name: str, value: int) -> None:
    await db[c.COUNTERS].update_one({"_id": name}, {"$max": {"seq": value}}, upsert=True)


GIRL_CODE_PREFIX = "KVP"


def girl_code(taluka_code: int, village_code: int, seq: int, prefix: str = "KVP", pad: int = 3) -> str:
    """<prefix>-<taluka no.>-<village no.>-<girl no. within the village>, e.g. KVP-01-03-045."""
    clean_prefix = (prefix or "KVP").rstrip("-")
    return f"{clean_prefix}-{taluka_code:02d}-{village_code:02d}-{seq:0{pad}d}"


def village_counter(village_id) -> str:
    return f"girl:village:{village_id}"


async def next_code(db: AsyncDatabase, coll: str, query: dict) -> int:
    """Next free number for a taluka (within all talukas) or a village (within its taluka)."""
    last = await db[coll].find_one({**query, "code": {"$type": "int"}}, sort=[("code", -1)])
    return (last["code"] if last else 0) + 1


async def next_girl_code(db: AsyncDatabase, village: dict) -> tuple[str, int]:
    """The next Girl ID in this village. Talukas and villages get a number the first time it is needed."""
    taluka = await db[c.TALUKAS].find_one({"_id": village["taluka_id"]})
    if taluka.get("code") is None:
        taluka["code"] = await next_code(db, c.TALUKAS, {})
        await db[c.TALUKAS].update_one({"_id": taluka["_id"]}, {"$set": {"code": taluka["code"]}})
    if village.get("code") is None:
        village["code"] = await next_code(db, c.VILLAGES, {"taluka_id": village["taluka_id"]})
        await db[c.VILLAGES].update_one({"_id": village["_id"]}, {"$set": {"code": village["code"]}})
    setting = await db[c.APP_SETTINGS].find_one({"key": "girl_id"})
    prefix = (setting.get("value") or {}).get("prefix", "KVP") if setting else "KVP"
    pad = (setting.get("value") or {}).get("pad", 3) if setting else 3
    seq = await next_sequence(db, village_counter(village["_id"]))
    return girl_code(taluka["code"], village["code"], seq, prefix=prefix, pad=pad), seq


async def next_case_code(db: AsyncDatabase) -> str:
    seq = await next_sequence(db, "case")
    return f"CASE-{seq:05d}"
