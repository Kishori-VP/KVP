"""Volunteers only see children of their own villages' Bal Panchayats (and girls of their own villages)."""
import uuid

from app.core.security import hash_password
from app.utils.dates import utcnow

API = "/api/v1"


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def _login(client, mongo, role, village_ids):
    phone = "8" + str(uuid.uuid4().int)[:9]
    now = utcnow()
    mongo.users.insert_one({
        "name": f"{role} user", "phone": phone, "password_hash": hash_password("pass12345"), "role": role,
        "is_active": True, "village_ids": village_ids, "village_id": village_ids[0] if village_ids else None,
        "created_at": now, "updated_at": now,
    })
    r = ok(client.post(f"{API}/auth/login", json={"identifier": phone, "password": "pass12345"}))
    return {"Authorization": f"Bearer {r['access_token']}"}


def test_volunteer_sees_only_own_village_children(client, mongo, admin):
    from bson import ObjectId

    tag = uuid.uuid4().hex[:6]
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": f"ScopeT-{tag}", "district": "District S"}), 201)
    va = ok(client.post(f"{API}/villages", headers=admin, json={"name": f"ScopeA-{tag}", "taluka_id": t["id"]}), 201)
    vb = ok(client.post(f"{API}/villages", headers=admin, json={"name": f"ScopeB-{tag}", "taluka_id": t["id"]}), 201)

    # Village A's Bal Panchayat also lists village B as a member village (as one live group does).
    bp_a = ok(client.post(f"{API}/groups", headers=admin, json={
        "name": f"BP-A-{tag}", "village_id": va["id"], "group_type": "bal_panchayat", "member_village_ids": [vb["id"]],
    }), 201)
    bp_b = ok(client.post(f"{API}/groups", headers=admin, json={
        "name": f"BP-B-{tag}", "village_id": vb["id"], "group_type": "bal_panchayat",
    }), 201)
    ok(client.post(f"{API}/children", headers=admin, json={"group_id": bp_a["id"], "name": f"Achild{tag}", "gender": "boy"}), 201)
    ok(client.post(f"{API}/children", headers=admin, json={"group_id": bp_b["id"], "name": f"Bchild{tag}", "gender": "boy"}), 201)

    girl_a = ok(client.post(f"{API}/girls", headers=admin, json={
        "name": f"Agirl{tag}", "age": 14, "village_id": va["id"], "bal_panchayat_id": bp_a["id"]}), 201)
    girl_b = ok(client.post(f"{API}/girls", headers=admin, json={
        "name": f"Bgirl{tag}", "age": 13, "village_id": vb["id"], "bal_panchayat_id": bp_a["id"]}), 201)

    vol = _login(client, mongo, "volunteer", [ObjectId(vb["id"])])
    a1 = _login(client, mongo, "admin_1", [])

    # --- girls: list, search, detail
    names = {g["name"] for g in ok(client.get(f"{API}/girls", headers=vol, params={"page_size": 500}))["items"]}
    assert f"Bgirl{tag}" in names and f"Agirl{tag}" not in names
    assert ok(client.get(f"{API}/girls", headers=vol, params={"q": f"Agirl{tag}"}))["total"] == 0
    assert ok(client.get(f"{API}/girls", headers=vol, params={"village_id": va["id"], "q": tag}))["total"] == 1  # still B only
    assert client.get(f"{API}/girls/{girl_a['id']}", headers=vol).status_code == 404
    ok(client.get(f"{API}/girls/{girl_b['id']}", headers=vol))

    # --- Bal Panchayat children: list, search, group filter, village filter
    kids = {k["name"] for k in ok(client.get(f"{API}/children", headers=vol, params={"page_size": 500}))["items"]}
    assert f"Bchild{tag}" in kids and f"Achild{tag}" not in kids
    assert ok(client.get(f"{API}/children", headers=vol, params={"q": f"Achild{tag}"}))["total"] == 0
    assert ok(client.get(f"{API}/children", headers=vol, params={"group_id": bp_a["id"]}))["total"] == 0
    assert ok(client.get(f"{API}/children", headers=vol, params={"village_id": va["id"], "q": f"Achild{tag}"}))["total"] == 0

    # --- group detail: the shared village-A group shows no members and only village-B girls
    g = ok(client.get(f"{API}/groups/{bp_a['id']}", headers=vol))
    assert g["members"] == [] and {x["name"] for x in g["girls"]} == {f"Bgirl{tag}"}
    assert ok(client.get(f"{API}/groups/{bp_b['id']}", headers=vol))["member_count"] == 1

    # --- group picker for the Children page: only village B's own Bal Panchayats
    picker = ok(client.get(f"{API}/groups", headers=vol, params={
        "village_id": vb["id"], "group_type": "bal_panchayat", "home_village_only": True}))["items"]
    assert [x["id"] for x in picker] == [bp_b["id"]]

    # --- admins are unchanged and see both villages
    for h in (admin, a1):
        kids = {k["name"] for k in ok(client.get(f"{API}/children", headers=h, params={"q": tag}))["items"]}
        assert kids == {f"Achild{tag}", f"Bchild{tag}"}
        assert ok(client.get(f"{API}/girls", headers=h, params={"q": tag}))["total"] == 2
        ok(client.get(f"{API}/girls/{girl_a['id']}", headers=h))
        g = ok(client.get(f"{API}/groups/{bp_a['id']}", headers=h))
        assert g["member_count"] == 1 and g["girl_count"] == 2
