"""Feed every record to the Ask AI index in one go (no request time limit).

    python -m app.scripts.ai_sync            # add new / changed records, remove deleted ones
    python -m app.scripts.ai_sync --force    # rewrite and re-embed everything
    python -m app.scripts.ai_sync --changes  # only apply changes since the last sync
    python -m app.scripts.ai_sync --no-embed # skip adding embeddings (they fill in slowly: free tier
                                             # allows ~30k tokens a minute)

Uses MONGODB_URI and GEMINI_API_KEY from backend/.env.
"""
import argparse
import asyncio
import time

from pymongo import AsyncMongoClient

from app.core.config import settings
from app.services import ai_index


async def main(force: bool, changes_only: bool, no_embed: bool = False) -> None:
    client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True)
    db = client[settings.mongodb_db_name]
    try:
        if changes_only:
            print(await ai_index.sync_changes(db, budget=120))
            return
        start = time.monotonic()
        last = {"coll": None}

        def progress(run, coll):
            if coll != last["coll"]:
                print(f"  {coll} …", flush=True)
                last["coll"] = coll

        run = await ai_index.full_sync(db, force=force, progress=progress)
        if run.get("busy"):
            print(run["message"])
            return
        print(f"Done in {time.monotonic() - start:.0f}s: {run['new']} new, {run['updated']} updated, "
              f"{run['unchanged']} unchanged, {run['removed'] + run.get('stale_removed', 0)} removed.")
        if run.get("embed_note"):
            print(f"Note: some records are keyword-only for now: {run['embed_note'][:200]}")
        if not no_embed:
            print("Adding embeddings to keyword-only records (paced to the Gemini free-tier limit)…", flush=True)

            def show(n):
                if n % 100 < 25:
                    print(f"  {n} embedded", flush=True)

            n = await ai_index.backfill_embeddings(db, max_chunks=None, wait_on_limit=True, progress=show)
            print(f"Embedded {n} more chunks.")
        index = db["ai_knowledge_chunks"]
        print(f"Index: {await index.count_documents({})} chunks, "
              f"{await index.count_documents({'retrieval_mode': 'vector'})} with embeddings. "
              f"Vector search index: {await ai_index.ensure_vector_index(db)}")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--changes", action="store_true")
    parser.add_argument("--no-embed", action="store_true", help="skip the slow embedding backfill")
    args = parser.parse_args()
    asyncio.run(main(args.force, args.changes, args.no_embed))
