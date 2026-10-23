"""One-off migration for multi-village volunteers.

Fills users.village_ids (and the primary users.village_id / group_ids) from each volunteer's
current assignments, then replaces the old "one village per volunteer" indexes.

    python -m app.seed.migrate_multi_village          # dry run: shows what would change
    python -m app.seed.migrate_multi_village --apply  # writes the changes
"""

import asyncio
import sys

from pymongo import AsyncMongoClient

from app.core.config import settings
from app.db import collections as c
from app.db.indexes import ensure_indexes
from app.services.assignments import current_assignments, sync_user


async def main(apply: bool) -> None:
    client = AsyncMongoClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    names = {v["_id"]: v["name"] async for v in db[c.VILLAGES].find({}, {"name": 1})}
    async for u in db[c.USERS].find({"role": "volunteer"}):
        current = await current_assignments(db, u["_id"])
        new = [a["village_id"] for a in current]
        old = u.get("village_ids")
        if old == new:
            continue
        print(f"{u['name']}: village_ids {[names.get(v) for v in (old or [])]} -> {[names.get(v) for v in new]}"
              + ("" if new or not u.get("village_id") else "  (WARNING: profile has a village but no current assignment)"))
        if apply:
            await sync_user(db, u["_id"])
    if apply:
        await ensure_indexes(db)
        print("Indexes updated.")
    else:
        print("Dry run only. Re-run with --apply to write the changes.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
