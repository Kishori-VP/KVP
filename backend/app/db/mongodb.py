from datetime import UTC

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings

_client: AsyncMongoClient | None = None


async def connect_to_mongo(uri: str | None = None) -> None:
    global _client
    if _client is not None:
        return
    _client = AsyncMongoClient(
        uri or settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
        tzinfo=UTC,
    )


async def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass
        _client = None


def get_database() -> AsyncDatabase:
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            tz_aware=True,
            tzinfo=UTC,
        )
    return _client[settings.mongodb_db_name]
