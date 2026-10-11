from datetime import date

from bson import ObjectId
from fastapi import APIRouter

from app.core.deps import Db, Pagination, Stakeholder
from app.db import collections as c
from app.utils.dates import day_range
from app.utils.mongo import ObjectIdStr, oid, paginate

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    db: Db,
    _: Stakeholder,
    pg: Pagination,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: ObjectIdStr | None = None,
    action: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    query: dict = {}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        # entity ids are ObjectIds for records and plain strings for settings keys
        query["entity_id"] = {"$in": [entity_id, oid(entity_id)]} if ObjectId.is_valid(entity_id) else entity_id
    if actor_id:
        query["actor_id"] = oid(actor_id)
    if action:
        query["action"] = action
    if start_date or end_date:
        start, end = day_range(start_date or date(2000, 1, 1), end_date or date(2100, 1, 1))
        query["at"] = {"$gte": start, "$lt": end}
    return await paginate(db[c.AUDIT_LOGS], query, pg.page, pg.page_size, sort=[("at", -1)])
