import uuid
from datetime import date, timedelta
from bson import ObjectId
import pytest
from app.core.security import hash_password
from app.utils.dates import utcnow

API = "/api/v1"


def _phone():
    return "9" + str(uuid.uuid4().int)[:9]


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def test_super_admin_crud_everything(client, mongo):
    now = utcnow()
    sa_phone = _phone()
    mongo.users.insert_one({
        "name": "Super Admin All", "email": f"{sa_phone}@test.org", "phone": sa_phone,
        "password_hash": hash_password("pass12345"), "role": "super_admin", "is_active": True,
        "village_ids": [], "created_at": now, "updated_at": now,
    })
    r_sa = client.post(f"{API}/auth/login", json={"identifier": sa_phone, "password": "pass12345"})
    assert r_sa.status_code == 200
    h = {"Authorization": f"Bearer {r_sa.json()['access_token']}"}

    # 1. VILLAGES & TALUKAS (CRUD)
    t = ok(client.post(f"{API}/talukas", headers=h, json={"name": f"Taluka-{sa_phone[-4:]}", "district": "District All"}), 201)
    tid = t["id"]
    v = ok(client.post(f"{API}/villages", headers=h, json={"name": f"Village-{sa_phone[-4:]}", "taluka_id": tid}), 201)
    vid = v["id"]
    # Edit village
    v_updated = ok(client.patch(f"{API}/villages/{vid}", headers=h, json={"name_mr": "गाव"}), 200)
    assert v_updated["name_mr"] == "गाव"
    # Read village
    v_read = ok(client.get(f"{API}/villages/{vid}", headers=h), 200)
    assert v_read["id"] == vid

    # 2. VOLUNTEERS / USERS (CRUD)
    vol_phone = _phone()
    vol = ok(client.post(f"{API}/users", headers=h, json={
        "name": "Tai All", "phone": vol_phone, "password": "pass12345", "role": "volunteer", "village_id": vid
    }), 201)
    vol_id = vol["id"]
    # Read volunteer
    vol_read = ok(client.get(f"{API}/volunteers/{vol_id}", headers=h), 200)
    assert vol_read["name"] == "Tai All"
    # Edit volunteer
    vol_edit = ok(client.patch(f"{API}/users/{vol_id}", headers=h, json={"name": "Tai All Updated"}), 200)
    assert vol_edit["name"] == "Tai All Updated"

    # 3. GROUPS (CRUD)
    grp = ok(client.post(f"{API}/groups", headers=h, json={
        "name": f"Kishori-{sa_phone[-4:]}", "village_id": vid, "group_type": "kishori", "responsible_volunteer_id": vol_id
    }), 201)
    gid = grp["id"]
    # Edit group
    grp_edit = ok(client.patch(f"{API}/groups/{gid}", headers=h, json={"name": f"Kishori-Edit-{sa_phone[-4:]}"}), 200)
    assert grp_edit["name"] == f"Kishori-Edit-{sa_phone[-4:]}"
    # Read group
    grp_read = ok(client.get(f"{API}/groups/{gid}", headers=h), 200)
    assert grp_read["id"] == gid

    # Bal Panchayat group for Children test
    bp = ok(client.post(f"{API}/groups", headers=h, json={
        "name": f"BP-{sa_phone[-4:]}", "village_id": vid, "group_type": "bal_panchayat"
    }), 201)
    bpid = bp["id"]

    # 4. GIRLS (CRUD)
    g_body = {
        "name": "Kavita Super", "village_id": vid, "group_id": gid, "bal_panchayat_id": bpid,
        "age": 14, "school_status": "studying", "household": {"father_name": "Ramesh"}
    }
    girl = ok(client.post(f"{API}/girls", headers=h, json=g_body), 201)
    girl_id = girl["id"]
    assert girl["name"] == "Kavita Super"
    # Read girl
    girl_read = ok(client.get(f"{API}/girls/{girl_id}", headers=h), 200)
    assert girl_read["id"] == girl_id
    # Edit girl
    girl_edit = ok(client.patch(f"{API}/girls/{girl_id}", headers=h, json={"name": "Kavita Super Edit"}), 200)
    assert girl_edit["name"] == "Kavita Super Edit"

    # Health record on girl (CRUD)
    health_body = {
        "recorded_on": str(date.today()), "hb_level": 11.5, "weight_kg": 40, "height_cm": 150,
        "observations": {"ifa_tablets": True, "hb_test_method": "digital"}
    }
    h_rec = ok(client.post(f"{API}/girls/{girl_id}/health", headers=h, json=health_body), 201)
    h_rec_id = h_rec["id"]
    assert h_rec["hb_level"] == 11.5
    # Read health
    h_list = ok(client.get(f"{API}/girls/{girl_id}/health", headers=h), 200)
    assert len(h_list["records"]) >= 1
    # Edit health
    h_upd = ok(client.patch(f"{API}/girls/{girl_id}/health/{h_rec_id}", headers=h, json={"hb_level": 12.0}), 200)
    assert h_upd["hb_level"] == 12.0
    # Delete health
    del_h = client.delete(f"{API}/girls/{girl_id}/health/{h_rec_id}", headers=h)
    assert del_h.status_code == 204

    # 5. CHILDREN in Bal Panchayat (CRUD)
    ch_body = {
        "group_id": bpid, "name": "Rohan Pawar", "standard": "7th", "phone": _phone(),
        "gender": "boy", "girl_id": None
    }
    ch = ok(client.post(f"{API}/children", headers=h, json=ch_body), 201)
    ch_id = ch["id"]
    assert ch["name"] == "Rohan Pawar"
    # Read children
    ch_list = ok(client.get(f"{API}/children", headers=h, params={"group_id": bpid}), 200)
    assert any(c["name"] == "Rohan Pawar" for c in ch_list["items"])
    # Edit child
    ch_edit = ok(client.patch(f"{API}/children/{bpid}/{ch_id}", headers=h, json={"standard": "8th"}), 200)
    assert ch_edit["standard"] == "8th"
    # Delete child
    del_ch = client.delete(f"{API}/children/{bpid}/{ch_id}", headers=h)
    assert del_ch.status_code == 204
    ch_list_after = ok(client.get(f"{API}/children", headers=h, params={"group_id": bpid}), 200)
    assert not any(c.get("id") == ch_id for c in ch_list_after["items"])

    # 6. CASES (CRUD)
    case = ok(client.post(f"{API}/cases", headers=h, json={
        "girl_id": girl_id, "title": "School Dropout Risk", "category": "school_dropout", "severity": "medium"
    }), 201)
    case_id = case["id"]
    # Read case
    case_read = ok(client.get(f"{API}/cases/{case_id}", headers=h), 200)
    assert case_read["id"] == case_id
    # Edit case
    case_edit = ok(client.patch(f"{API}/cases/{case_id}", headers=h, json={"title": "Updated Dropout Risk"}), 200)
    assert case_edit["title"] == "Updated Dropout Risk"
    # Delete case
    del_case = client.delete(f"{API}/cases/{case_id}", headers=h)
    assert del_case.status_code == 204
    assert client.get(f"{API}/cases/{case_id}", headers=h).status_code == 404

    # 7. EVENTS (CRUD)
    ev_date = str(date.today() + timedelta(days=7))
    ev = ok(client.post(f"{API}/events", headers=h, json={
        "title": "Nutrition Workshop", "event_type": "kishori_meeting", "village_id": vid,
        "event_date": ev_date, "start_time": "11:00", "end_time": "13:00"
    }), 201)
    ev_id = ev["id"]
    # Read event
    ev_read = ok(client.get(f"{API}/events/{ev_id}", headers=h), 200)
    assert ev_read["id"] == ev_id
    # Edit event
    ev_edit = ok(client.patch(f"{API}/events/{ev_id}", headers=h, json={"title": "Updated Nutrition Workshop"}), 200)
    assert ev_edit["title"] == "Updated Nutrition Workshop"
    # Delete event
    del_ev = client.delete(f"{API}/events/{ev_id}", headers=h)
    assert del_ev.status_code == 204
    assert client.get(f"{API}/events/{ev_id}", headers=h).status_code == 404

    # 8. TARGETS (CRUD)
    tg = ok(client.post(f"{API}/targets", headers=h, json={
        "volunteer_ids": [vol_id], "village_id": vid, "target_type": "home_visits",
        "target_value": 15, "period_type": "monthly", "period_start": str(date.today())
    }), 201)["created"][0]
    tg_id = tg["id"]
    # Read target
    tg_read = ok(client.get(f"{API}/targets/{tg_id}", headers=h), 200)
    assert tg_read["id"] == tg_id
    # Delete target
    del_tg = client.delete(f"{API}/targets/{tg_id}", headers=h)
    assert del_tg.status_code == 204
    assert client.get(f"{API}/targets/{tg_id}", headers=h).status_code == 404

    # 9. CONTACTS (CRUD)
    ct = ok(client.post(f"{API}/contacts", headers=h, json={
        "category": "talathi", "name": "Talathi Patil", "mobile": _phone(), "village_id": vid
    }), 201)
    ct_id = ct["id"]
    # Read contact
    ct_read = ok(client.get(f"{API}/contacts/{ct_id}", headers=h), 200)
    assert ct_read["id"] == ct_id
    # Edit contact
    ct_edit = ok(client.patch(f"{API}/contacts/{ct_id}", headers=h, json={"designation": "Head Talathi"}), 200)
    assert ct_edit["designation"] == "Head Talathi"
    # Delete contact
    del_ct = client.delete(f"{API}/contacts/{ct_id}", headers=h)
    assert del_ct.status_code == 204

    # 10. DELETE GIRL
    del_girl = client.delete(f"{API}/girls/{girl_id}", headers=h)
    assert del_girl.status_code == 204
    assert client.get(f"{API}/girls/{girl_id}", headers=h).status_code == 404

    # 11. DELETE GROUP
    del_grp = client.delete(f"{API}/groups/{gid}", headers=h)
    assert del_grp.status_code == 204
    assert client.get(f"{API}/groups/{gid}", headers=h).status_code == 404

    # 12. DELETE VOLUNTEER
    del_vol = client.delete(f"{API}/users/{vol_id}", headers=h)
    assert del_vol.status_code == 204
    assert client.get(f"{API}/volunteers/{vol_id}", headers=h).status_code == 404

    # 13. DELETE VILLAGE & TALUKA
    del_v = client.delete(f"{API}/villages/{vid}", headers=h)
    assert del_v.status_code == 204
    assert client.get(f"{API}/villages/{vid}", headers=h).status_code == 404

    del_t = client.delete(f"{API}/talukas/{tid}", headers=h)
    assert del_t.status_code == 204
