from datetime import UTC

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings

_client: AsyncMongoClient | None = None


async def connect_to_mongo(uri: str | None = None) -> None:
    global _client
    _client = AsyncMongoClient(
        uri or settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
        tzinfo=UTC,
    )


async def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_database() -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialised")
    return _client[settings.mongodb_db_name]
