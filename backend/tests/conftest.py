import os
import tempfile

# Configure before the app (and its settings) are imported.
os.environ["MONGODB_URI"] = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
os.environ["MONGODB_DB_NAME"] = "kishori_vikas_test"
os.environ["SCHEDULER_ENABLED"] = "false"
# Keep tests independent of the developer's local .env (push, email).
os.environ["VAPID_PUBLIC_KEY"] = ""
os.environ["VAPID_PRIVATE_KEY"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
_tmp = tempfile.mkdtemp(prefix="kvp-test-")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["REPORTS_DIR"] = os.path.join(_tmp, "reports")
os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "dGVzdC1rZXktZm9yLXVuaXQtdGVzdHMtb25seS0xMjM="

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.core.config import settings
from app.core.security import hash_password
from app.seed.defaults import DEFAULT_LOOKUPS
from app.utils.dates import utcnow

ADMIN_PHONE, ADMIN_PASSWORD = "9000000001", "admin-pass-123"


def _bootstrap():
    if "mongodb.net" in settings.mongodb_uri or "atlas" in settings.mongodb_uri.lower():
        raise RuntimeError("Refusing to run tests against remote MongoDB cluster! Set TEST_MONGODB_URI.")
    client = MongoClient(settings.mongodb_uri)
    client.drop_database(settings.mongodb_db_name)
    db = client[settings.mongodb_db_name]
    now = utcnow()
    db.users.insert_one({
        "name": "Test Coordinator", "email": "admin@test.org", "phone": ADMIN_PHONE,
        "password_hash": hash_password(ADMIN_PASSWORD), "role": "super_admin", "village_id": None, "taluka_id": None,
        "group_ids": [], "contact": {}, "is_active": True, "created_at": now, "updated_at": now,
    })
    for type_, items in DEFAULT_LOOKUPS.items():
        for order, (code, label, label_mr, attrs) in enumerate(items):
            db.lookups.insert_one({"type": type_, "code": code, "label": label, "label_mr": label_mr,
                                   "attributes": attrs, "order": order, "is_active": True, "is_system": True})
    return client


@pytest.fixture(scope="session")
def mongo():
    client = _bootstrap()
    yield client[settings.mongodb_db_name]
    client.drop_database(settings.mongodb_db_name)
    client.close()


@pytest.fixture(scope="session")
def client(mongo):
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client):
    r = client.post("/api/v1/auth/login", json={"identifier": ADMIN_PHONE, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
