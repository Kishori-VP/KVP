"""Knowledge index for the Ask AI assistant.

The index (collection ``ai_knowledge_chunks``) holds one or more text chunks per database record,
with a Gemini embedding for the records worth semantic search.

It is kept up to date in two ways, both safe on serverless hosts (Vercel), where nothing may run
after a request finishes:

* ``full_sync`` scans every record. It is resumable: each call works for at most ``budget``
  seconds, saves a cursor, and the next call carries on. The CLI ``python -m app.scripts.ai_sync``
  runs it to the end in one go.
* ``sync_changes`` reads the MongoDB change stream from the last saved resume token, so every
  insert, update and delete made since the previous sync — from any screen or script — is applied.
  It runs after each successful write request, before each chat answer and on the scheduler.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import DeleteMany, ReplaceOne, UpdateMany
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure, PyMongoError

from app.core.config import settings
from app.db import collections as c

log = logging.getLogger(__name__)

# Collections fed to the assistant. Cases and health records of minors are left out for child protection.
RAG_COLLECTIONS = [
    c.TALUKAS,
    c.VILLAGES,
    c.GROUPS,
    c.CONTACTS,
    c.GIRLS,
    c.HOME_VISITS,
    c.ACTIVITY_REPORTS,
    c.EVENTS,
    c.TARGETS,
    c.VOLUNTEER_ASSIGNMENTS,
    c.VOLUNTEER_ATTENDANCE,
    c.USERS,
    c.LOOKUPS,
    c.REPORT_TEMPLATES,
    c.NOTIFICATIONS,
    c.AUDIT_LOGS,
]
# High-volume logs are found by keyword search only, which keeps them out of the embedding quota.
KEYWORD_ONLY_COLLECTIONS = {c.NOTIFICATIONS, c.AUDIT_LOGS, c.VOLUNTEER_ATTENDANCE}

EMBED_DIM = 768
EMBED_BATCH = 100  # Gemini's batch limit
EMBED_CHARS = 1500  # embed the start of each chunk only (~750 tokens)
EMBED_TOKENS_PER_CALL = 1500  # measured: larger requests are refused on the free tier
EMBED_TOKENS_PER_MINUTE = 5000  # measured on the free tier: about 8 chunks a minute get through (Gemini says 30,000)
VECTOR_INDEX_NAME = "ai_vector_index"
STATE_COLLECTION = "ai_index_state"
STATE_ID = "state"
EMBED_PAUSE = timedelta(minutes=30)  # after a quota error, stop calling the embedding API for a while
DOC_BATCH = 100

SENSITIVE_KEYS = {
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "api_key", "gemini_api_key", "credentials_encrypted",
    "credentials_encryption_key", "jwt_secret_key", "smtp_password",
    "private_key", "vapid_private_key", "endpoint", "file_path",
    "storage_path", "upload_path", "connection_string", "mongodb_uri",
    "check_in_photo", "check_out_photo", "photo", "face_descriptor",
    "fingerprint", "aadhaar_number", "aadhaar", "aadhaar_front", "aadhaar_back", "id_proof",
}


# ------------------------------------------------------------------ models

_cached: dict[str, Any] = {}


def get_models():
    """Return (chat model, embedding model), cached per process."""
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI is not configured. Set GEMINI_API_KEY in backend/.env and restart the backend.",
        )
    key = (api_key, settings.gemini_chat_model, settings.gemini_embedding_model)
    if _cached.get("key") == key:
        return _cached["chat"], _cached["embed"]
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    except ImportError as exc:
        log.exception("LangChain Gemini packages are missing")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "AI dependencies are missing. Install backend/requirements.txt.") from exc
    # One retry only: the default (6 retries with back-off) turns a rate limit into a request timeout.
    chat = ChatGoogleGenerativeAI(model=settings.gemini_chat_model, google_api_key=api_key, max_retries=1, timeout=40)
    embed = GoogleGenerativeAIEmbeddings(model=settings.gemini_embedding_model, google_api_key=api_key,
                                         output_dimensionality=EMBED_DIM)
    _cached.update(key=key, chat=chat, embed=embed)
    return chat, embed


def provider_error(exc: Exception) -> str:
    detail = str(exc)
    if settings.gemini_api_key:
        detail = detail.replace(settings.gemini_api_key, "[redacted]")
    return " ".join(detail.split())[:500]


# ------------------------------------------------------------------ chunking

def _safe(value: Any) -> Any:
    """Convert MongoDB values to JSON-safe values and remove sensitive fields."""
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            k = str(key).lower()
            if k in SENSITIVE_KEYS or any(t in k for t in ("password_hash", "secret_key", "credentials_encrypted")):
                continue
            out[key] = _safe(child)
        return out
    if isinstance(value, list):
        return [_safe(item) for item in value[:200]]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "[binary omitted]"
    if isinstance(value, str):
        if value.startswith("data:image/") or (len(value) > 500 and "base64" in value[:30]):
            return "[image omitted]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


_lookup_cache: dict[str, Any] = {"at": 0.0, "maps": None}


async def build_lookup_maps(db: AsyncDatabase, max_age: float = 0) -> dict[str, dict[str, str]]:
    """Names for village, taluka, group and user ids, so chunks read naturally."""
    if max_age and _lookup_cache["maps"] and time.time() - _lookup_cache["at"] < max_age:
        return _lookup_cache["maps"]
    villages = {str(v["_id"]): v.get("name") or str(v["_id"]) async for v in db[c.VILLAGES].find({}, {"name": 1})}
    talukas = {str(t["_id"]): t.get("name") or str(t["_id"]) async for t in db[c.TALUKAS].find({}, {"name": 1})}
    groups = {}
    async for g in db[c.GROUPS].find({}, {"name": 1, "group_type": 1}):
        name, gtype = g.get("name") or "", g.get("group_type") or ""
        groups[str(g["_id"])] = f"{name} ({gtype})" if gtype else name
    users = {}
    async for u in db[c.USERS].find({}, {"full_name": 1, "name": 1, "role": 1}):
        uname, role = u.get("full_name") or u.get("name") or "User", u.get("role") or ""
        users[str(u["_id"])] = f"{uname} ({role})" if role else uname
    maps = {"villages": villages, "talukas": talukas, "groups": groups, "users": users}
    _lookup_cache.update(at=time.time(), maps=maps)
    return maps


def _enrich(doc: dict, lookups: dict[str, dict[str, str]] | None) -> dict:
    if not lookups:
        return doc
    out = dict(doc)
    for field, table, name in (("village_id", "villages", "village_name"), ("taluka_id", "talukas", "taluka_name"),
                               ("group_id", "groups", "group_name")):
        key = str(doc.get(field) or "")
        if key in lookups[table]:
            out[name] = lookups[table][key]
    vol = str(doc.get("volunteer_id") or doc.get("assigned_to") or doc.get("responsible_volunteer_id") or "")
    if vol in lookups["users"]:
        out["volunteer_name"] = lookups["users"][vol]
    return out


def chunks_for_document(collection: str, doc: dict, lookups: dict | None = None) -> list[dict]:
    """Split a record into searchable chunks with a readable header and a content hash."""
    record_id = str(doc.get("_id", "unknown"))
    safe_doc = _safe(_enrich(doc, lookups))
    header = [f"Collection: {collection}", f"Record ID: {record_id}"]
    if safe_doc.get("programme"):
        header.append(f"Programme: {safe_doc['programme']}")
    elif safe_doc.get("project"):
        header.append(f"Project: {safe_doc['project']}")
    for key, label in (("village_name", "Village"), ("taluka_name", "Taluka"), ("group_name", "Group"),
                       ("girl_code", "Beneficiary/Girl Code"), ("name", "Name"), ("title", "Title")):
        if safe_doc.get(key):
            header.append(f"{label}: {safe_doc[key]}")
    head = " | ".join(header)
    body = json.dumps(safe_doc, ensure_ascii=False, default=str)

    max_chars, overlap = 4000, 250
    chunks, start = [], 0
    while True:
        text = f"{head}\n{body[start:start + max_chars]}"
        chunks.append({
            "source_collection": collection,
            "source_id": record_id,
            "chunk_no": len(chunks),
            "content": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
        if start + max_chars >= len(body):
            return chunks
        start += max_chars - overlap


def _indexable(doc: dict | None) -> bool:
    return bool(doc) and not doc.get("is_deleted")


# ------------------------------------------------------------------ state

def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt and dt.tzinfo is None else dt


async def get_state(db: AsyncDatabase) -> dict:
    return await db[STATE_COLLECTION].find_one({"_id": STATE_ID}) or {"_id": STATE_ID}


async def _set_state(db: AsyncDatabase, fields: dict, unset: list[str] | None = None) -> None:
    update: dict = {"$set": fields}
    if unset:
        update["$unset"] = {k: "" for k in unset}
    await db[STATE_COLLECTION].update_one({"_id": STATE_ID}, update, upsert=True)


# ------------------------------------------------------------------ writing chunks

def _embed_text(ch: dict) -> str:
    # The header and first fields carry the meaning; the full text stays in `content` for keyword search.
    return ch["content"][:EMBED_CHARS]


def _tokens(text: str) -> int:
    return len(text) // 2 + 1  # measured: about 2 characters per token (Marathi text included)


def _batches(chunks: list[dict]) -> list[list[dict]]:
    """Group chunks so each embedding call stays well under the per-minute token allowance."""
    out, cur, tokens = [], [], 0
    for ch in chunks:
        t = _tokens(_embed_text(ch))
        if cur and (len(cur) >= EMBED_BATCH or tokens + t > EMBED_TOKENS_PER_CALL):
            out.append(cur)
            cur, tokens = [], 0
        cur.append(ch)
        tokens += t
    if cur:
        out.append(cur)
    return out


_token_log: list[tuple[float, int]] = []  # (time, tokens) of this process's recent embedding calls


async def _throttle(tokens: int, wait: bool) -> bool:
    """Keep this process under the per-minute token allowance. Returns False if it would have to wait."""
    while True:
        now = time.monotonic()
        _token_log[:] = [(t, n) for t, n in _token_log if now - t < 60]
        used = sum(n for _, n in _token_log)
        if used + tokens <= EMBED_TOKENS_PER_MINUTE:
            _token_log.append((now, tokens))
            return True
        if not wait:
            return False
        await asyncio.sleep(max(1.0, 60 - (now - _token_log[0][0]) + 0.5))


class _Embedder:
    """Embeds chunk texts. After a quota error it stops for a while so syncs stay fast,
    or, with ``wait_on_limit`` (the CLI), waits out a per-minute limit and carries on."""

    def __init__(self, db: AsyncDatabase, state: dict, *, wait_on_limit: bool = False):
        self.db = db
        self.model = None
        self.note: str | None = None
        self.wait_on_limit = wait_on_limit
        paused = _aware(state.get("embed_paused_until"))
        if paused and paused > _now() and not wait_on_limit:
            self.note = state.get("embed_pause_reason") or "Embedding paused after a quota error"
            return
        try:
            self.model = get_models()[1]
        except HTTPException as exc:
            self.note = str(exc.detail)

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        for _attempt in range(30 if self.wait_on_limit else 1):
            if not self.model or not texts:
                return None
            if not await _throttle(sum(_tokens(t) for t in texts), self.wait_on_limit):
                self.note = "Embedding skipped to stay under the per-minute quota"
                return None
            try:
                vectors = await asyncio.wait_for(self.model.aembed_documents(texts), 60)
                return vectors if len(vectors) == len(texts) else None
            except Exception as exc:
                self.note = provider_error(exc)
                low = self.note.lower()
                if not ("quota" in low or "429" in low or ("resource" in low and "exhaust" in low)):
                    if self.wait_on_limit:  # long CLI run: ride out a temporary provider error
                        log.info("Embedding error, retrying in 15s: %s", self.note[:200])
                        await asyncio.sleep(15)
                        continue
                    log.warning("Embedding failed; using keyword search for these records: %s", self.note)
                    self.model = None
                    return None
                daily = "per day" in low or "perday" in low or "_day" in low or "daily" in low
                if self.wait_on_limit and not daily:
                    log.info("Embedding per-minute limit reached; waiting a minute…")
                    await asyncio.sleep(65)
                    continue
                pause = EMBED_PAUSE if daily else timedelta(seconds=65)
                log.warning("Embedding quota reached; keyword search only for %s: %s", pause, self.note)
                await _set_state(self.db, {"embed_paused_until": _now() + pause, "embed_pause_reason": self.note})
                self.model = None
                return None
        return None


async def _embed_into(chunks: list[dict], embedder: _Embedder) -> int:
    embedded = 0
    for batch in _batches(chunks):
        vectors = await embedder.embed([_embed_text(ch) for ch in batch])
        if not vectors:
            break
        for ch, vec in zip(batch, vectors):
            ch["embedding"] = vec
        embedded += len(batch)
    return embedded


async def _write_chunks(db: AsyncDatabase, chunks: list[dict], embedder: _Embedder) -> int:
    """Upsert chunks, embedding the ones from semantic collections. Returns how many got a vector."""
    embedded = await _embed_into([ch for ch in chunks if ch["source_collection"] not in KEYWORD_ONLY_COLLECTIONS],
                                 embedder)
    now = _now()
    ops = []
    for ch in chunks:
        ch["retrieval_mode"] = "vector" if ch.get("embedding") else "keyword"
        ch["indexed_at"] = now
        ops.append(ReplaceOne({"source_collection": ch["source_collection"], "source_id": ch["source_id"],
                               "chunk_no": ch["chunk_no"]}, ch, upsert=True))
    if ops:
        await db[c.AI_KNOWLEDGE_CHUNKS].bulk_write(ops, ordered=False)
    return embedded


def _needs_write(chunk: dict, existing: dict | None, force: bool, can_embed: bool) -> bool:
    if force or not existing or existing.get("content_hash") != chunk["content_hash"]:
        return True
    if chunk["source_collection"] in KEYWORD_ONLY_COLLECTIONS:
        return False
    # Same content: rewrite only to add (or fix the size of) a missing vector.
    return existing.get("emb_len", 0) != EMBED_DIM and (can_embed or existing.get("emb_len", 0) > 0)


async def _existing_chunks(db: AsyncDatabase, collection: str, ids: list[str]) -> dict[tuple[str, int], dict]:
    rows = db[c.AI_KNOWLEDGE_CHUNKS].find(
        {"source_collection": collection, "source_id": {"$in": ids}},
        {"source_id": 1, "chunk_no": 1, "content_hash": 1, "emb_len": {"$size": {"$ifNull": ["$embedding", []]}}},
    )
    return {(r["source_id"], r.get("chunk_no", 0)): r async for r in rows}


async def _apply_docs(db: AsyncDatabase, collection: str, docs: list[dict], lookups: dict, embedder: _Embedder,
                      *, force: bool = False, run_id: str | None = None) -> dict:
    """Bring the chunks of these records up to date. Records that are gone or soft-deleted lose their chunks."""
    index = db[c.AI_KNOWLEDGE_CHUNKS]
    live = [d for d in docs if _indexable(d)]
    gone_ids = [str(d["_id"]) for d in docs if not _indexable(d)]
    ids = [str(d["_id"]) for d in live]
    existing = await _existing_chunks(db, collection, ids) if ids else {}
    seen_sources = {sid for sid, _ in existing}
    writes, unchanged, counts = [], [], {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}
    keep: dict[str, int] = {}
    can_embed = embedder.model is not None
    for doc in live:
        chunks = chunks_for_document(collection, doc, lookups)
        sid = chunks[0]["source_id"]
        keep[sid] = len(chunks)
        changed = False
        for ch in chunks:
            if _needs_write(ch, existing.get((sid, ch["chunk_no"])), force, can_embed):
                if run_id:
                    ch["sync_run"] = run_id
                writes.append(ch)
                changed = True
            else:
                unchanged.append((sid, ch["chunk_no"]))
        if changed:
            counts["updated" if sid in seen_sources else "new"] += 1
        else:
            counts["unchanged"] += 1
    await _write_chunks(db, writes, embedder)

    ops = []
    if run_id and unchanged:
        by_source: dict[str, list[int]] = {}
        for sid, no in unchanged:
            by_source.setdefault(sid, []).append(no)
        ops += [UpdateMany({"source_collection": collection, "source_id": sid, "chunk_no": {"$in": nos}},
                           {"$set": {"sync_run": run_id}}) for sid, nos in by_source.items()]
    # Drop chunks past a record's new end (it got shorter) and chunks of removed records.
    ops += [DeleteMany({"source_collection": collection, "source_id": sid, "chunk_no": {"$gte": n}}) for sid, n in keep.items()
            if (sid, n) in existing]
    if gone_ids:
        had = await index.distinct("source_id", {"source_collection": collection, "source_id": {"$in": gone_ids}})
        if had:
            ops.append(DeleteMany({"source_collection": collection, "source_id": {"$in": had}}))
            counts["removed"] = len(had)
    if ops:
        await index.bulk_write(ops, ordered=False)
    counts["embed_note"] = embedder.note
    return counts


async def backfill_embeddings(db: AsyncDatabase, *, max_chunks: int | None = 15,
                              wait_on_limit: bool = False, progress=None) -> int:
    """Add vectors to chunks that were stored keyword-only (e.g. while the quota was used up)."""
    embedder = _Embedder(db, await get_state(db), wait_on_limit=wait_on_limit)
    index = db[c.AI_KNOWLEDGE_CHUNKS]
    query = {"retrieval_mode": "keyword", "source_collection": {"$nin": list(KEYWORD_ONLY_COLLECTIONS)}}
    done = 0
    while embedder.model and (max_chunks is None or done < max_chunks):
        limit = min(EMBED_BATCH, max_chunks - done) if max_chunks else EMBED_BATCH
        rows = await index.find(query, {"content": 1}).limit(limit).to_list(limit)
        if not rows:
            break
        got = await _embed_into(rows, embedder)
        if not got:
            break
        await index.bulk_write([UpdateMany({"_id": r["_id"]}, {"$set": {"embedding": r["embedding"], "retrieval_mode": "vector"}})
                                for r in rows if r.get("embedding")], ordered=False)
        done += got
        if progress:
            progress(done)
    return done


# ------------------------------------------------------------------ change sync

_change_streams_unsupported = False


async def _open_stream(db: AsyncDatabase, token):
    pipeline = [{"$match": {"ns.coll": {"$in": RAG_COLLECTIONS},
                            "operationType": {"$in": ["insert", "update", "replace", "delete"]}}}]
    return await db.watch(pipeline, full_document="updateLookup", start_after=token, max_await_time_ms=150)


async def init_change_token(db: AsyncDatabase, *, overwrite: bool = False) -> bool:
    """Remember the current point of the change stream so later syncs pick up from here."""
    global _change_streams_unsupported
    if _change_streams_unsupported:
        return False
    if not overwrite and (await get_state(db)).get("resume_token"):
        return True
    try:
        stream = await _open_stream(db, None)
        try:
            await stream.try_next()
            token = stream.resume_token
        finally:
            await stream.close()
    except OperationFailure as exc:
        if exc.code in (40573, 40324, 136):  # standalone server / unsupported stage / no oplog
            _change_streams_unsupported = True
            return False
        raise
    if token:
        await _set_state(db, {"resume_token": token, "change_sync_at": _now()})
    return bool(token)


async def sync_changes(db: AsyncDatabase, budget: float = 6.0) -> dict:
    """Index every record created, edited or deleted since the last sync. Never raises."""
    global _change_streams_unsupported
    if _change_streams_unsupported:
        return {"status": "unsupported"}
    deadline = time.monotonic() + budget
    try:
        state = await get_state(db)
        token = state.get("resume_token")
        if not token:
            await init_change_token(db)
            return {"status": "initialised"}
        changed: dict[tuple[str, str], dict | None] = {}
        stream = await _open_stream(db, token)
        try:
            last_token = token
            while time.monotonic() < deadline - 2 and len(changed) < 400:
                event = await stream.try_next()
                if event is None:
                    last_token = stream.resume_token or last_token
                    break
                coll, doc_id = event["ns"]["coll"], event["documentKey"]["_id"]
                changed[(coll, str(doc_id))] = event.get("fullDocument") or {"_id": doc_id, "is_deleted": True}
                last_token = stream.resume_token
        finally:
            await stream.close()

        result = {"status": "ok", "records": len(changed), "new": 0, "updated": 0, "removed": 0}
        if changed:
            lookups = await build_lookup_maps(db, max_age=60)
            embedder = _Embedder(db, state)
            by_coll: dict[str, list[dict]] = {}
            for (coll, _), doc in changed.items():
                by_coll.setdefault(coll, []).append(doc)
            run = state.get("full_sync") or {}
            run_id = run.get("run_id") if not run.get("done", True) else None
            for coll, docs in by_coll.items():
                counts = await _apply_docs(db, coll, docs, lookups, embedder, run_id=run_id)
                for k in ("new", "updated", "removed"):
                    result[k] += counts[k]
            result["embed_note"] = embedder.note
        await _set_state(db, {"resume_token": last_token, "change_sync_at": _now()})
        return result
    except OperationFailure as exc:
        if exc.code in (40573, 40324, 136):
            _change_streams_unsupported = True
            return {"status": "unsupported"}
        if exc.code in (280, 286, 260) or "resume" in str(exc).lower():
            # The saved point fell off the oplog: start again from now and ask for a full sync.
            log.warning("AI change stream history lost; a full sync is needed: %s", exc)
            await _set_state(db, {"needs_full_sync": True}, unset=["resume_token"])
            return {"status": "history_lost"}
        log.warning("AI change sync failed: %s", exc)
        return {"status": "error", "error": str(exc)[:200]}
    except (PyMongoError, asyncio.TimeoutError, Exception) as exc:  # never break the request that triggered it
        log.warning("AI change sync failed: %s", exc)
        return {"status": "error", "error": str(exc)[:200]}


# ------------------------------------------------------------------ full sync

async def full_sync(db: AsyncDatabase, *, budget: float | None = None, force: bool = False,
                    progress=None) -> dict:
    """Scan every record and bring the index up to date. Resumable: call again until ``done`` is true.

    ``force`` starts a fresh run that rewrites (and re-embeds) every chunk.
    """
    deadline = time.monotonic() + budget if budget else None
    state = await get_state(db)
    lock = _aware(state.get("full_sync_lock_until"))
    if lock and lock > _now():
        run = state.get("full_sync") or {}
        return {**run, "busy": True, "message": "A sync is already running. Try again in a moment."}

    run = state.get("full_sync") or {}
    if force or run.get("done", True) or not run.get("run_id"):
        await init_change_token(db, overwrite=bool(state.get("needs_full_sync")))
        run = {"run_id": uuid.uuid4().hex, "started_at": _now(), "force": force, "done": False,
               "collection_index": 0, "last_id": None, "new": 0, "updated": 0, "unchanged": 0, "removed": 0,
               "total_records": sum([await db[col].estimated_document_count() for col in RAG_COLLECTIONS])}
    lock_span = (budget or 600) + 30
    await _set_state(db, {"full_sync": run, "full_sync_lock_until": _now() + timedelta(seconds=lock_span)})

    try:
        lookups = await build_lookup_maps(db)
        embedder = _Embedder(db, state)
        batches = 0
        while run["collection_index"] < len(RAG_COLLECTIONS):
            if deadline and batches and time.monotonic() > deadline:
                break
            coll = RAG_COLLECTIONS[run["collection_index"]]
            query = {"_id": {"$gt": run["last_id"]}} if run["last_id"] is not None else {}
            docs = await db[coll].find(query).sort("_id", 1).limit(DOC_BATCH).to_list(DOC_BATCH)
            if not docs:
                run["collection_index"] += 1
                run["last_id"] = None
                continue
            counts = await _apply_docs(db, coll, docs, lookups, embedder, force=run.get("force", False),
                                       run_id=run["run_id"])
            for k in ("new", "updated", "unchanged", "removed"):
                run[k] += counts[k]
            run["last_id"] = docs[-1]["_id"]
            run["embed_note"] = embedder.note
            batches += 1
            if not deadline:  # long CLI run: keep the lock fresh
                await _set_state(db, {"full_sync_lock_until": _now() + timedelta(seconds=lock_span)})
            await _set_state(db, {"full_sync": run})
            if progress:
                progress(run, coll)

        if run["collection_index"] >= len(RAG_COLLECTIONS):
            # Everything was visited: drop chunks of records that no longer exist.
            res = await db[c.AI_KNOWLEDGE_CHUNKS].delete_many(
                {"sync_run": {"$ne": run["run_id"]}, "indexed_at": {"$lt": _aware(run["started_at"])}})
            run["stale_removed"] = res.deleted_count
            run["done"] = True
            run["finished_at"] = _now()
            await ensure_vector_index(db)
            await _set_state(db, {"full_sync": run, "needs_full_sync": False})
    finally:
        await _set_state(db, {}, unset=["full_sync_lock_until"])
    run["records_done"] = run["new"] + run["updated"] + run["unchanged"] + run["removed"]
    return run


# ------------------------------------------------------------------ search index

async def ensure_vector_index(db: AsyncDatabase) -> str:
    """Create the Atlas Vector Search index if it is missing. Returns its status."""
    index = db[c.AI_KNOWLEDGE_CHUNKS]
    try:
        existing = [i async for i in await index.list_search_indexes(VECTOR_INDEX_NAME)]
        if existing:
            return existing[0].get("status", "exists")
        from pymongo.operations import SearchIndexModel
        await index.create_search_index(SearchIndexModel(
            name=VECTOR_INDEX_NAME, type="vectorSearch",
            definition={"fields": [
                {"type": "vector", "path": "embedding", "numDimensions": EMBED_DIM, "similarity": "cosine"},
                {"type": "filter", "path": "source_collection"},
            ]},
        ))
        return "created"
    except Exception as exc:  # not Atlas, or search indexes unavailable: chat falls back to keyword search
        log.info("Vector search index unavailable: %s", exc)
        return "unavailable"
