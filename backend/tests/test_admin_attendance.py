"""Admin-1 / Admin-2 mark their own daily NoteCam attendance, same as volunteers."""

from datetime import date, datetime, timedelta, timezone

from bson import ObjectId

API = "/api/v1"
GPS = {"lat": 19.0760, "lng": 72.8777, "accuracy_m": 12}


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def _login(client, admin, name, phone, role):
    ok(client.post(f"{API}/users", headers=admin, json={
        "name": name, "phone": phone, "password": f"{role}-pass-1", "role": role}), 201)
    tok = ok(client.post(f"{API}/auth/login", json={"identifier": phone, "password": f"{role}-pass-1"}))
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_admin_roles_take_attendance(client, admin, mongo):
    a1 = _login(client, admin, "Attendance Admin One", "9000000901", "admin_1")
    a2 = _login(client, admin, "Attendance Admin Two", "9000000902", "admin_2")

    for headers, role in ((a1, "admin_1"), (a2, "admin_2")):
        assert ok(client.get(f"{API}/attendance/today", headers=headers))["checked_in"] is False
        rec = ok(client.post(f"{API}/attendance/check-in", headers=headers,
                             json={"gps": GPS, "photo": "data:image/jpeg;base64,AAAA"}))
        assert rec["role"] == role and rec["status"] == "present" and rec["check_in"]
        # attendance is taken once per day
        assert client.post(f"{API}/attendance/check-in", headers=headers, json={"gps": GPS}).status_code == 400
        # minimum 5 hours on duty before check-out; /today exposes the countdown target
        status = ok(client.get(f"{API}/attendance/today", headers=headers))
        allowed = datetime.fromisoformat(status["checkout_allowed_at"])
        checked_in = datetime.fromisoformat(status["record"]["check_in_at"])
        assert status["min_work_hours"] == 5 and allowed - checked_in == timedelta(hours=5)
        early = client.post(f"{API}/attendance/check-out", headers=headers, json={"gps": GPS})
        assert early.status_code == 400 and "Minimum 5 hours" in early.json()["detail"]
        # simulate 5 hours having passed
        mongo.volunteer_attendance.update_one(
            {"_id": ObjectId(rec["id"])},
            {"$set": {"check_in_at": datetime.now(timezone.utc) - timedelta(hours=5, minutes=1)}})
        assert ok(client.get(f"{API}/attendance/today", headers=headers))["checkout_allowed_at"] < status["server_now"]
        out = ok(client.post(f"{API}/attendance/check-out", headers=headers,
                             json={"gps": GPS, "photo": "data:image/jpeg;base64,BBBB"}))
        assert out["check_out"]
        today = ok(client.get(f"{API}/attendance/today", headers=headers))
        assert today["checked_in"] and today["checked_out"]

    # Admin-2 stays read-only otherwise: no back-dated self attendance, no register edits.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert client.post(f"{API}/attendance/check-in", headers=a2,
                       json={"attendance_date": yesterday, "gps": GPS}).status_code == 400
    me = ok(client.get(f"{API}/auth/me", headers=a2))
    assert client.post(f"{API}/attendance/batch", headers=a2, json={"entries": [
        {"volunteer_id": me["id"], "attendance_date": yesterday, "status": "present"}]}).status_code == 403

    # Both admins show up on the attendance register.
    rows = ok(client.get(f"{API}/attendance", headers=admin, params={"include_photos": False}))
    roles = {r["volunteer_name"]: r["role"] for r in rows}
    assert roles["Attendance Admin One"] == "admin_1" and roles["Attendance Admin Two"] == "admin_2"
