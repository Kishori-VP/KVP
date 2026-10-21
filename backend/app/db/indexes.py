from pymongo import ASCENDING, DESCENDING, IndexModel, TEXT
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c

INDEXES: dict[str, list[IndexModel]] = {
    c.USERS: [
        IndexModel("email", unique=True, partialFilterExpression={"email": {"$type": "string"}}),
        IndexModel("phone", unique=True),
        IndexModel([("role", ASCENDING), ("is_active", ASCENDING)]),
        IndexModel("village_id"),
    ],
    c.VOLUNTEER_ASSIGNMENTS: [
        # Allows a Tai (volunteer) to be assigned to multiple villages concurrently.
        IndexModel(
            [("volunteer_id", ASCENDING), ("village_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"is_current": True},
            name="current_assignment_per_volunteer_village",
        ),
        IndexModel([("volunteer_id", ASCENDING), ("start_date", DESCENDING)]),
        IndexModel("village_id"),
    ],
    c.TALUKAS: [IndexModel([("name", ASCENDING), ("district", ASCENDING)], unique=True)],
    c.VILLAGES: [
        IndexModel([("name", ASCENDING), ("taluka_id", ASCENDING)], unique=True),
        IndexModel("taluka_id"),
        IndexModel("aliases"),
    ],
    c.GROUPS: [
        IndexModel([("village_id", ASCENDING), ("group_type", ASCENDING), ("name", ASCENDING)], unique=True),
        IndexModel("responsible_volunteer_id"),
    ],
    c.CONTACTS: [IndexModel([("village_id", ASCENDING), ("category", ASCENDING)]), IndexModel("taluka_id")],
    c.GIRLS: [
        IndexModel("girl_code", unique=True),
        IndexModel("girl_seq"),
        IndexModel([("village_id", ASCENDING), ("group_id", ASCENDING)]),
        IndexModel("taluka_id"),
        IndexModel("school_status"),
        IndexModel("dob"),
        IndexModel("is_deleted"),
        IndexModel([("name", TEXT), ("household.father_name", TEXT), ("household.head_name", TEXT)],
                   default_language="none"),
    ],
    c.HEALTH_RECORDS: [IndexModel([("girl_id", ASCENDING), ("recorded_on", DESCENDING)]), IndexModel("village_id")],
    c.CASES: [
        IndexModel("case_code", unique=True),
        IndexModel([("girl_id", ASCENDING), ("opened_at", DESCENDING)]),
        IndexModel([("status", ASCENDING), ("severity", ASCENDING)]),
        IndexModel("village_id"),
        IndexModel("assigned_to"),
        IndexModel("due_date"),
    ],
    c.HOME_VISITS: [
        IndexModel([("volunteer_id", ASCENDING), ("visit_date", DESCENDING)]),
        IndexModel([("village_id", ASCENDING), ("visit_date", DESCENDING)]),
        IndexModel("girl_ids"),
        IndexModel("status"),
        IndexModel("client_record_id", unique=True, partialFilterExpression={"client_record_id": {"$type": "string"}}),
    ],
    c.ACTIVITY_REPORTS: [
        IndexModel([("volunteer_id", ASCENDING), ("report_date", ASCENDING)], unique=True),
        IndexModel("client_record_id", unique=True, partialFilterExpression={"client_record_id": {"$type": "string"}}),
        IndexModel([("village_id", ASCENDING), ("report_date", DESCENDING)]),
    ],
    c.EVENTS: [
        IndexModel([("village_id", ASCENDING), ("start_at", DESCENDING)]),
        IndexModel([("status", ASCENDING), ("start_at", ASCENDING)]),
        IndexModel("responsible_volunteer_id"),
        IndexModel("event_type"),
        IndexModel("attendance.girl_id"),
    ],
    c.MEDIA: [
        IndexModel([("entity_type", ASCENDING), ("entity_id", ASCENDING)]),
        IndexModel([("sha256", ASCENDING), ("entity_type", ASCENDING), ("entity_id", ASCENDING)], unique=True),
    ],
    c.TARGETS: [
        IndexModel([("volunteer_id", ASCENDING), ("period_start", DESCENDING)]),
        IndexModel([("village_id", ASCENDING), ("period_end", DESCENDING)]),
        IndexModel("status"),
    ],
    c.NOTIFICATIONS: [
        IndexModel([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel("dedupe_key", unique=True, partialFilterExpression={"dedupe_key": {"$type": "string"}}),
    ],
    c.PUSH_SUBSCRIPTIONS: [IndexModel("endpoint", unique=True), IndexModel("user_id")],
    c.MESSAGE_OUTBOX: [
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("entity_type", ASCENDING), ("entity_id", ASCENDING)]),
        IndexModel("dedupe_key", unique=True, partialFilterExpression={"dedupe_key": {"$type": "string"}}),
    ],
    c.SYNC_STATUS: [IndexModel([("user_id", ASCENDING), ("device_id", ASCENDING)], unique=True),
                    IndexModel("last_report_at")],
    c.LOOKUPS: [IndexModel([("type", ASCENDING), ("code", ASCENDING)], unique=True)],
    c.APP_SETTINGS: [IndexModel("key", unique=True)],
    c.PROVIDER_CONFIGS: [IndexModel([("provider_type", ASCENDING), ("provider_name", ASCENDING)], unique=True)],
    c.REPORT_TEMPLATES: [IndexModel("name", unique=True), IndexModel([("report_type", ASCENDING), ("is_active", ASCENDING)])],
    c.REPORT_SCHEDULES: [IndexModel([("is_active", ASCENDING), ("next_run_at", ASCENDING)])],
    c.GENERATED_REPORTS: [IndexModel("created_at")],
    c.AI_KNOWLEDGE_CHUNKS: [
        IndexModel([("source_collection", ASCENDING), ("source_id", ASCENDING), ("chunk_no", ASCENDING)], unique=True),
        IndexModel([("content", TEXT)], default_language="none"),
        IndexModel([("retrieval_mode", ASCENDING)]),
        IndexModel([("content_hash", ASCENDING)]),
    ],
    c.VOLUNTEER_ATTENDANCE: [IndexModel([("volunteer_id", ASCENDING), ("attendance_date", DESCENDING)], unique=True), IndexModel([("attendance_date", DESCENDING), ("status", ASCENDING)])],
    c.AUDIT_LOGS: [
        IndexModel([("at", DESCENDING)]),
        IndexModel([("entity_type", ASCENDING), ("entity_id", ASCENDING), ("at", DESCENDING)]),
        IndexModel("actor_id"),
    ],
}


async def ensure_indexes(db: AsyncDatabase) -> None:
    try:
        await db[c.VOLUNTEER_ASSIGNMENTS].drop_index("one_current_assignment_per_volunteer")
    except Exception:
        pass
    for coll_name, indexes in INDEXES.items():
        await db[coll_name].create_indexes(indexes)
