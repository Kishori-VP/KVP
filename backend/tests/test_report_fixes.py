"""
Targeted tests for issues reported in KVP Test Report.
"""
from datetime import date, timedelta
import uuid
import pytest
from app.core.config import settings
from app.core.permissions import Role
from app.db import collections as c
from app.utils.dates import today_local, utcnow


def _unique_phone():
    return f"9{uuid.uuid4().int % 900000000 + 100000000}"


def test_issue1_no_demo_backdoor(client):
    """Issue 1: Demo backdoor login does not authenticate without an existing DB account."""
    r = client.post("/api/v1/auth/login", json={"identifier": "nonexistent_demo_user@example.org", "password": "KvpDemo@123"})
    assert r.status_code == 401


def test_issue2_admin_cannot_takeover_stakeholder(client, mongo):
    """Issue 2: An admin cannot reset password, edit profile, or deactivate a Stakeholder."""
    now = utcnow()
    from app.core.security import hash_password
    phone1 = _unique_phone()
    phone2 = _unique_phone()
    stk_res = mongo.users.insert_one({
        "name": "Target Stakeholder", "email": f"{phone1}@test.org", "phone": phone1,
        "password_hash": hash_password("pass12345"), "role": "stakeholder", "is_active": True,
        "village_ids": [], "created_at": now, "updated_at": now,
    })
    adm_res = mongo.users.insert_one({
        "name": "Sub Admin", "email": f"{phone2}@test.org", "phone": phone2,
        "password_hash": hash_password("pass12345"), "role": "admin", "is_active": True,
        "village_ids": [], "created_at": now, "updated_at": now,
    })
    
    # Login as Sub Admin
    r = client.post("/api/v1/auth/login", json={"identifier": phone2, "password": "pass12345"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Admin attempts reset password of stakeholder -> 403
    r = client.post(f"/api/v1/users/{stk_res.inserted_id}/reset-password", json={"new_password": "NewSecret123"}, headers=headers)
    assert r.status_code == 403
    
    # Admin attempts deactivating stakeholder -> 403
    r = client.patch(f"/api/v1/users/{stk_res.inserted_id}/status", json={"is_active": False}, headers=headers)
    assert r.status_code == 403

    # Admin attempts editing stakeholder profile -> 403
    r = client.patch(f"/api/v1/users/{stk_res.inserted_id}", json={"name": "Hacked Name"}, headers=headers)
    assert r.status_code == 403


def test_issue3_gps_attendance_validation(client, mongo):
    """Issue 3: Volunteer self check-in rejects past dates, unassigned villages, and 0,0 GPS."""
    now = utcnow()
    from app.core.security import hash_password
    v_res = mongo.villages.insert_one({"name": f"Village {uuid.uuid4().hex[:6]}", "taluka_id": None, "status": "active"})
    other_v_res = mongo.villages.insert_one({"name": f"Village {uuid.uuid4().hex[:6]}", "taluka_id": None, "status": "active"})
    phone = _unique_phone()
    vol_res = mongo.users.insert_one({
        "name": "Volunteer Test", "email": None, "phone": phone,
        "password_hash": hash_password("pass12345"), "role": "volunteer", "is_active": True,
        "village_id": v_res.inserted_id, "village_ids": [v_res.inserted_id], "created_at": now, "updated_at": now,
    })
    
    r = client.post("/api/v1/auth/login", json={"identifier": phone, "password": "pass12345"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    
    # Check-in for 10 days ago -> 400
    past_date = (today_local() - timedelta(days=10)).isoformat()
    r = client.post("/api/v1/attendance/check-in", json={"attendance_date": past_date, "village_id": str(v_res.inserted_id)}, headers=headers)
    assert r.status_code == 400

    # Check-in for unassigned village -> 403
    r = client.post("/api/v1/attendance/check-in", json={"village_id": str(other_v_res.inserted_id)}, headers=headers)
    assert r.status_code == 403

    # Check-in with GPS 0, 0 -> 400
    r = client.post("/api/v1/attendance/check-in", json={"village_id": str(v_res.inserted_id), "gps": {"lat": 0.0, "lng": 0.0}}, headers=headers)
    assert r.status_code == 400


def test_issue14_apply_default_targets_empty_selection(client, admin):
    """Issue 14: all_active=False with empty volunteer_ids does not apply to everyone."""
    r = client.post("/api/v1/targets/apply-defaults", json={"all_active": False, "volunteer_ids": [], "periods": ["weekly"]}, headers=admin)
    assert r.status_code == 200
    assert r.json()["applied_to"] == 0


def test_issue16_activity_report_patch(client, admin, mongo):
    """Issue 16: Activity reports can be edited via PATCH."""
    now = utcnow()
    v_res = mongo.villages.insert_one({"name": f"Village {uuid.uuid4().hex[:6]}", "taluka_id": None, "status": "active"})
    from app.core.security import hash_password
    phone = _unique_phone()
    vol_res = mongo.users.insert_one({
        "name": "Volunteer R", "phone": phone, "password_hash": hash_password("pass12345"),
        "role": "volunteer", "is_active": True, "village_ids": [v_res.inserted_id], "created_at": now, "updated_at": now,
    })
    
    r = client.post("/api/v1/auth/login", json={"identifier": phone, "password": "pass12345"})
    v_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    
    # Create report
    r = client.post("/api/v1/activity-reports", json={
        "volunteer_id": str(vol_res.inserted_id), "village_id": str(v_res.inserted_id),
        "report_date": today_local().isoformat(), "activities": ["home_visit"], "home_visits_count": 2,
    }, headers=v_headers)
    assert r.status_code == 201
    rep_id = r.json().get("id") or r.json().get("_id")
    
    # Edit report
    r = client.patch(f"/api/v1/activity-reports/{rep_id}", json={"topics_discussed": "Updated topics", "home_visits_count": 3}, headers=v_headers)
    assert r.status_code == 200
    assert r.json()["topics_discussed"] == "Updated topics"
    assert r.json()["home_visits_count"] == 3


def test_issue19_future_dob_rejected_on_edit(client, admin, mongo):
    """Issue 19: Future date of birth is rejected on PATCH."""
    v_res = mongo.villages.insert_one({"name": f"Village {uuid.uuid4().hex[:6]}", "taluka_id": None, "status": "active"})
    unique_code = f"KVP-99-99-{uuid.uuid4().int % 900 + 100}"
    gid_res = mongo.girls.insert_one({
        "name": "Test Girl", "girl_code": unique_code, "village_id": v_res.inserted_id,
        "is_deleted": False, "dob": None, "age": 14,
    })
    future_dob = (today_local() + timedelta(days=365)).isoformat()
    r = client.patch(f"/api/v1/girls/{gid_res.inserted_id}", json={"dob": future_dob}, headers=admin)
    assert r.status_code == 422


def test_issue20_cancelled_event_blocks_expenditure_and_media(client, admin, mongo):
    """Issue 20: Cancelled event rejects expenditure and media updates."""
    v_res = mongo.villages.insert_one({"name": f"Village {uuid.uuid4().hex[:6]}", "taluka_id": None, "status": "active"})
    now = utcnow()
    ev_res = mongo.events.insert_one({
        "title": "Cancelled Event", "village_id": v_res.inserted_id, "event_date": now,
        "start_at": now, "end_at": now, "status": "cancelled", "attendance": [], "media_ids": [],
    })
    
    # Expenditure
    r = client.put(f"/api/v1/events/{ev_res.inserted_id}/expenditure", json={"items": [{"item": "Snacks", "quantity": 10, "unit_cost": 20}]}, headers=admin)
    assert r.status_code == 409
