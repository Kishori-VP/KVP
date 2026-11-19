"""Uploaded files live in MongoDB GridFS, so they survive serverless hosts with temporary disks."""
from bson import ObjectId

from app.utils.dates import utcnow

API = "/api/v1"
JPEG = b"\xff\xd8\xff\xe0" + b"photo-bytes" * 50


def _event(mongo):
    now = utcnow()
    return str(mongo.events.insert_one({
        "title": "Storage test", "status": "planned", "event_date": now, "start_at": now, "end_at": now,
        "attendance": [], "media_ids": [], "is_deleted": False,
    }).inserted_id)


def test_upload_is_stored_in_gridfs_and_served(client, admin, mongo):
    event_id = _event(mongo)
    # "image/jpg" (sent by some phones) is accepted as JPEG.
    r = client.post(f"{API}/media", headers=admin, files={"file": ("visit.jpg", JPEG, "image/jpg")},
                    data={"entity_type": "event", "entity_id": event_id})
    assert r.status_code == 201, r.text
    media = r.json()
    assert media["content_type"] == "image/jpeg" and "path" not in media
    doc = mongo.media.find_one({"_id": ObjectId(media["id"])})
    assert mongo["media_files.files"].count_documents({"_id": doc["gridfs_id"]}) == 1

    got = client.get(f"{API}/media/{media['id']}/file", headers=admin)
    assert got.status_code == 200 and got.content == JPEG and got.headers["content-type"] == "image/jpeg"

    # Same file again: returns the existing record, no second copy.
    again = client.post(f"{API}/media", headers=admin, files={"file": ("visit.jpg", JPEG, "image/jpeg")},
                        data={"entity_type": "event", "entity_id": event_id}).json()
    assert again["duplicate"] and again["id"] == media["id"]

    assert client.delete(f"{API}/media/{media['id']}", headers=admin, params={"reason": "test cleanup"}).status_code == 204
    assert mongo["media_files.files"].count_documents({"_id": doc["gridfs_id"]}) == 0


def test_unsupported_and_missing_files(client, admin, mongo):
    event_id = _event(mongo)
    bad = client.post(f"{API}/media", headers=admin, files={"file": ("notes.txt", b"hi", "text/plain")},
                      data={"entity_type": "event", "entity_id": event_id})
    assert bad.status_code == 415 and "JPG" in bad.json()["detail"]

    # A record saved to disk before GridFS whose file is gone (temporary disk) reports 410, not a crash.
    legacy = mongo.media.insert_one({
        "entity_type": "event", "entity_id": ObjectId(event_id), "path": "2026/01/missing.jpg",
        "content_type": "image/jpeg", "sha256": "legacy", "sensitive": False, "uploaded_at": utcnow(),
    }).inserted_id
    assert client.get(f"{API}/media/{legacy}/file", headers=admin).status_code == 410


def test_report_files_and_template_attachments_live_in_gridfs(client, admin, mongo):
    tpl = client.post(f"{API}/reports/templates", headers=admin, json={
        "name": "GridFS template", "report_type": "programme_summary", "default_formats": ["pdf"]}).json()
    att = client.post(f"{API}/reports/templates/{tpl['id']}/attachments", headers=admin,
                      files={"file": ("Cover.pdf", b"%PDF-1.4 cover", "application/pdf")})
    assert att.status_code == 201, att.text
    entry = mongo.report_templates.find_one({"_id": ObjectId(tpl["id"])})["attachments"][0]
    assert entry.get("gridfs_id") and "path" not in entry
    got = client.get(f"{API}/reports/templates/{tpl['id']}/attachments/{entry['id']}", headers=admin)
    assert got.status_code == 200 and got.content == b"%PDF-1.4 cover"

    me = client.get(f"{API}/auth/me", headers=admin).json()
    shared = client.post(f"{API}/reports/templates/{tpl['id']}/share", headers=admin,
                         json={"recipient_user_ids": [me["id"]], "formats": ["pdf", "csv"]}).json()
    files = mongo.generated_reports.find_one({"_id": ObjectId(shared["id"])})["files"]
    assert {f["format"] for f in files} == {"pdf", "csv", "attachment"}
    assert all(f.get("gridfs_id") and "path" not in f for f in files)
    pdf = client.get(f"{API}/reports/generated/{shared['id']}/download", headers=admin, params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    copy = client.get(f"{API}/reports/generated/{shared['id']}/download", headers=admin,
                      params={"format": "attachment", "name": "Cover.pdf"})
    assert copy.content == b"%PDF-1.4 cover"

    # Removing the template's attachment keeps the generated report's own copy.
    assert client.delete(f"{API}/reports/templates/{tpl['id']}/attachments/{entry['id']}", headers=admin).status_code == 204
    assert mongo["report_files.files"].count_documents({"_id": entry["gridfs_id"]}) == 0
    assert client.get(f"{API}/reports/generated/{shared['id']}/download", headers=admin,
                      params={"format": "attachment", "name": "Cover.pdf"}).content == b"%PDF-1.4 cover"
