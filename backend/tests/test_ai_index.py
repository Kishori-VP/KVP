"""Ask AI knowledge index: full sync adds, updates, removes and resumes; chunk rules."""
import asyncio

from bson import ObjectId
from pymongo import AsyncMongoClient

from app.core.config import settings
from app.services import ai_index

DB_NAME = "kishori_vikas_ai_index_test"


def _run(coro_fn, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")  # keyword mode: no network calls

    async def go():
        client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True)
        await client.drop_database(DB_NAME)
        try:
            return await coro_fn(client[DB_NAME])
        finally:
            await client.drop_database(DB_NAME)
            await client.close()

    return asyncio.run(go())


async def _chunks(db, **q):
    return await db["ai_knowledge_chunks"].find(q).to_list(None)


def test_full_sync_adds_updates_and_removes(monkeypatch):
    async def scenario(db):
        village = ObjectId()
        await db.villages.insert_one({"_id": village, "name": "Palam"})
        g1, g2, g3 = ObjectId(), ObjectId(), ObjectId()
        await db.girls.insert_many([
            {"_id": g1, "name": "Asha", "girl_code": "G-1", "village_id": village, "password_hash": "x"},
            {"_id": g2, "name": "Meera", "girl_code": "G-2", "village_id": village},
            {"_id": g3, "name": "Gone", "girl_code": "G-3", "is_deleted": True},
        ])
        await db.audit_logs.insert_one({"summary": "Created girl G-1"})

        run = await ai_index.full_sync(db)
        assert run["done"] and run["new"] == 4 and run["removed"] == 0  # village, 2 girls, 1 audit log
        girls = await _chunks(db, source_collection="girls")
        assert {c["source_id"] for c in girls} == {str(g1), str(g2)}
        asha = next(c for c in girls if c["source_id"] == str(g1))
        assert "Village: Palam" in asha["content"] and "password_hash" not in asha["content"]
        assert asha["retrieval_mode"] == "keyword"

        # Second run: nothing changed.
        run = await ai_index.full_sync(db)
        assert run["new"] == 0 and run["updated"] == 0 and run["unchanged"] == 4

        # Edit one, soft-delete one, hard-delete the village, add one.
        await db.girls.update_one({"_id": g1}, {"$set": {"name": "Asha Patil"}})
        await db.girls.update_one({"_id": g2}, {"$set": {"is_deleted": True}})
        await db.villages.delete_one({"_id": village})
        await db.events.insert_one({"title": "Health camp"})
        run = await ai_index.full_sync(db)
        assert run["updated"] == 1 and run["new"] == 1 and run["removed"] == 1 and run["stale_removed"] == 1
        assert {c["source_id"] for c in await _chunks(db, source_collection="girls")} == {str(g1)}
        assert not await _chunks(db, source_collection="villages")
        assert "Asha Patil" in (await _chunks(db, source_collection="girls"))[0]["content"]

    _run(scenario, monkeypatch)


def test_full_sync_resumes_across_calls(monkeypatch):
    monkeypatch.setattr(ai_index, "DOC_BATCH", 5)

    async def scenario(db):
        await db.events.insert_many([{"title": f"Event {i}"} for i in range(23)])
        run = await ai_index.full_sync(db, budget=0.000001)  # stops after the first batch
        assert not run["done"] and 0 < run["records_done"] < 23
        calls = 1
        while not run["done"]:
            run = await ai_index.full_sync(db, budget=0.000001)
            calls += 1
        assert calls > 2 and run["new"] == 23
        assert await db["ai_knowledge_chunks"].count_documents({"source_collection": "events"}) == 23

    _run(scenario, monkeypatch)


def test_long_records_split_and_shrink(monkeypatch):
    async def scenario(db):
        gid = ObjectId()
        await db.groups.insert_one({"_id": gid, "name": "Big", "notes": "x" * 9000})
        await ai_index.full_sync(db)
        assert len(await _chunks(db, source_id=str(gid))) == 3
        await db.groups.update_one({"_id": gid}, {"$set": {"notes": "short"}})
        await ai_index.full_sync(db)
        assert len(await _chunks(db, source_id=str(gid))) == 1

    _run(scenario, monkeypatch)


def test_change_sync_is_a_noop_without_replica_set(monkeypatch):
    async def scenario(db):
        result = await ai_index.sync_changes(db)
        assert result["status"] in {"unsupported", "initialised", "ok"}

    _run(scenario, monkeypatch)


def test_successful_writes_trigger_index_update(client, admin, monkeypatch):
    calls = []

    async def fake_sync(db, budget=6.0):
        calls.append(budget)
        return {"status": "ok"}

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_index, "sync_changes", fake_sync)
    assert client.get("/api/v1/notifications", headers=admin).status_code == 200
    assert calls == []  # reads never trigger it
    assert client.post("/api/v1/notifications/read-all", headers=admin).status_code == 200
    assert len(calls) == 1
    assert client.post("/api/v1/notifications/read-all").status_code == 401
    assert len(calls) == 1  # failed writes don't either
