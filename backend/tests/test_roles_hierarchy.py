import uuid
from datetime import date, timedelta
import pytest
from app.core.security import hash_password
from app.utils.dates import utcnow

API = "/api/v1"


def _unique_phone():
    return "9" + str(uuid.uuid4().int)[:9]


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def test_super_admin_admin1_admin2_hierarchy(client, mongo):
    now = utcnow()
    
    # 1. Create users for the 3 roles
    sa_phone = _unique_phone()
    a1_phone = _unique_phone()
    a2_phone = _unique_phone()
    
    mongo.users.insert_one({
        "name": "Super Admin User", "email": f"{sa_phone}@test.org", "phone": sa_phone,
        "password_hash": hash_password("pass12345"), "role": "super_admin", "is_active": True,
        "village_ids": [], "created_at": now, "updated_at": now,
    })
    mongo.users.insert_one({
        "name": "Admin 1 User", "email": f"{a1_phone}@test.org", "phone": a1_phone,
        "password_hash": hash_password("pass12345"), "role": "admin_1", "is_active": True,
        "village_ids": [], "created_at": now, "updated_at": now,
    })
    mongo.users.insert_one({
        "name": "Admin 2 User", "email": f"{a2_phone}@test.org", "phone": a2_phone,
        "password_hash": hash_password("pass12345"), "role": "admin_2", "is_active": True,
        "village_ids": [], "created_at": now, "updated_at": now,
    })

    # Login SA
    r_sa = client.post(f"{API}/auth/login", json={"identifier": sa_phone, "password": "pass12345"})
    assert r_sa.status_code == 200
    h_sa = {"Authorization": f"Bearer {r_sa.json()['access_token']}"}

    # Login Admin-1
    r_a1 = client.post(f"{API}/auth/login", json={"identifier": a1_phone, "password": "pass12345"})
    assert r_a1.status_code == 200
    h_a1 = {"Authorization": f"Bearer {r_a1.json()['access_token']}"}

    # Login Admin-2
    r_a2 = client.post(f"{API}/auth/login", json={"identifier": a2_phone, "password": "pass12345"})
    assert r_a2.status_code == 200
    h_a2 = {"Authorization": f"Bearer {r_a2.json()['access_token']}"}

    # Setup taluka and village via SA
    t = ok(client.post(f"{API}/talukas", headers=h_sa, json={"name": f"Taluka-{sa_phone[-4:]}", "district": "District X"}), 201)
    v = ok(client.post(f"{API}/villages", headers=h_sa, json={"name": f"Village-{sa_phone[-4:]}", "taluka_id": t["id"]}), 201)
    vid = v["id"]

    # --- TEST SUPER ADMIN CAPABILITIES ---
    # SA can create volunteer
    vol_phone = _unique_phone()
    vol = ok(client.post(f"{API}/users", headers=h_sa, json={
        "name": "Field Volunteer", "phone": vol_phone, "password": "volPassword1",
        "role": "volunteer", "village_id": vid,
    }), 201)

    # SA can create contact and delete it
    c = ok(client.post(f"{API}/contacts", headers=h_sa, json={
        "category": "sarpanch", "name": "Sarpanch Test", "mobile": _unique_phone(), "village_id": vid
    }), 201)
    del_c = client.delete(f"{API}/contacts/{c['id']}", headers=h_sa)
    assert del_c.status_code == 204

    # --- TEST ADMIN-1 CAPABILITIES & RESTRICTIONS ---
    # Admin-1 can add Kishori groups
    grp = ok(client.post(f"{API}/groups", headers=h_a1, json={
        "name": f"Group-{a1_phone[-4:]}", "village_id": vid, "group_type": "kishori"
    }), 201)
    assert grp["name"] == f"Group-{a1_phone[-4:]}"

    # Admin-1 can add events
    ev_date = (date.today() + timedelta(days=2)).isoformat()
    ev = ok(client.post(f"{API}/events", headers=h_a1, json={
        "title": "Health Workshop", "event_type": "health_camp", "village_id": vid,
        "event_date": ev_date, "start_time": "10:00", "end_time": "12:00"
    }), 201)
    assert ev["title"] == "Health Workshop"

    # Admin-1 CANNOT add volunteers
    r_a1_add_vol = client.post(f"{API}/users", headers=h_a1, json={
        "name": "Forbidden Vol", "phone": _unique_phone(), "password": "pass12345",
        "role": "volunteer", "village_id": vid,
    })
    assert r_a1_add_vol.status_code == 403
    assert "Only Super Admin" in r_a1_add_vol.text

    # Admin-1 CANNOT delete records (e.g. contact, home visit, or cancel event)
    c2 = ok(client.post(f"{API}/contacts", headers=h_sa, json={
        "category": "sarpanch", "name": "Sarpanch Test 2", "mobile": _unique_phone(), "village_id": vid
    }), 201)
    r_a1_del_c = client.delete(f"{API}/contacts/{c2['id']}", headers=h_a1)
    assert r_a1_del_c.status_code == 403
    assert "Only Super Admin" in r_a1_del_c.text or "cannot delete" in r_a1_del_c.text.lower()

    # Admin-1 CANNOT cancel events
    r_a1_cancel_ev = client.post(f"{API}/events/{ev['id']}/cancel", headers=h_a1, json={"reason": "Rain"})
    assert r_a1_cancel_ev.status_code == 403

    # --- TEST ADMIN-2 (READ-ONLY MONITOR) CAPABILITIES & RESTRICTIONS ---
    # Admin-2 CAN read volunteers, users, events, groups, villages
    assert client.get(f"{API}/volunteers", headers=h_a2).status_code == 200
    assert client.get(f"{API}/users", headers=h_a2).status_code == 200
    assert client.get(f"{API}/events", headers=h_a2).status_code == 200
    assert client.get(f"{API}/groups", headers=h_a2).status_code == 200
    assert client.get(f"{API}/villages", headers=h_a2).status_code == 200

    # Admin-2 CANNOT create events
    r_a2_ev = client.post(f"{API}/events", headers=h_a2, json={
        "title": "Forbidden Event", "event_type": "health_camp", "village_id": vid,
        "event_date": ev_date, "start_time": "10:00", "end_time": "12:00"
    })
    assert r_a2_ev.status_code == 403
    assert "read-only" in r_a2_ev.text.lower()

    # Admin-2 CANNOT create groups
    r_a2_grp = client.post(f"{API}/groups", headers=h_a2, json={
        "name": "Forbidden Group", "village_id": vid, "group_type": "kishori"
    })
    assert r_a2_grp.status_code == 403
    assert "read-only" in r_a2_grp.text.lower()

    # Admin-2 CANNOT add volunteers
    r_a2_vol = client.post(f"{API}/users", headers=h_a2, json={
        "name": "Forbidden Vol 2", "phone": _unique_phone(), "password": "pass12345",
        "role": "volunteer", "village_id": vid,
    })
    assert r_a2_vol.status_code == 403

    # Admin-2 CANNOT update records (PATCH)
    r_a2_patch = client.patch(f"{API}/events/{ev['id']}", headers=h_a2, json={"title": "Hacked Title"})
    assert r_a2_patch.status_code == 403
    assert "read-only" in r_a2_patch.text.lower()

    # Admin-2 CANNOT delete records
    r_a2_del = client.delete(f"{API}/contacts/{c2['id']}", headers=h_a2)
    assert r_a2_del.status_code == 403
