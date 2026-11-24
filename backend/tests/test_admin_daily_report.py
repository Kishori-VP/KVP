"""Admin-1 / Admin-2 can be chosen on the daily activity report form, for any village."""

import uuid

from app.utils.dates import today_local

API = "/api/v1"


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def test_daily_report_for_admins(client, admin, mongo):
    village = mongo.villages.insert_one({"name": f"Village {uuid.uuid4().hex[:6]}", "taluka_id": None, "status": "active"})
    vid = str(village.inserted_id)
    today = today_local().isoformat()
    created = []
    try:
        _run(client, admin, vid, today, created)
    finally:
        # The test database is shared by the whole suite: leave no extra village, users or reports behind.
        mongo.activity_reports.delete_many({"village_id": village.inserted_id})
        mongo.users.delete_many({"_id": {"$in": created}})
        mongo.villages.delete_one({"_id": village.inserted_id})


def _run(client, admin, vid, today, created):
    from bson import ObjectId

    for role in ("admin_1", "admin_2"):
        person = ok(client.post(f"{API}/users", headers=admin, json={
            "name": f"Field Admin {role}", "phone": f"97{uuid.uuid4().int % 10**8:08d}", "password": "admin-pass-1", "role": role}), 201)
        created.append(ObjectId(person["id"]))

        # Admins have no assigned villages, so the village must be chosen.
        r = client.post(f"{API}/activity-reports", headers=admin, json={
            "volunteer_id": person["id"], "report_date": today, "activities": ["home_visit"]})
        assert r.status_code == 422 and "village" in r.json()["detail"].lower()

        rep = ok(client.post(f"{API}/activity-reports", headers=admin, json={
            "volunteer_id": person["id"], "village_id": vid, "report_date": today,
            "activities": ["home_visit"], "home_visits_count": 1}), 201)
        assert rep["volunteer_id"] == person["id"] and rep["village_id"] == vid
        assert rep["approval"]["status"] == "approved"

        listed = ok(client.get(f"{API}/activity-reports", headers=admin, params={"volunteer_id": person["id"]}))
        assert [x["id"] for x in listed["items"]] == [rep["id"]]

    # A super admin is still not a valid person for a daily report.
    me = ok(client.get(f"{API}/auth/me", headers=admin))
    r = client.post(f"{API}/activity-reports", headers=admin, json={
        "volunteer_id": me["id"], "village_id": vid, "report_date": today, "activities": ["home_visit"]})
    assert r.status_code == 404
