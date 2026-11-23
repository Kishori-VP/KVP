"""External girls: Super Admin and Admin-1 read and write, Admin-2 read only.
Media library: Super Admin and Admin-1 only, filterable by village and date."""

from datetime import UTC, date, datetime, timedelta

from bson import ObjectId

API = "/api/v1"


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def login_as(client, admin, role, phone):
    ok(client.post(f"{API}/users", headers=admin, json={
        "name": f"Access {role}", "phone": phone, "password": "access-pass-1", "role": role}), 201)
    tok = ok(client.post(f"{API}/auth/login", json={"identifier": phone, "password": "access-pass-1"}))
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_external_girls_access_by_role(client, admin):
    a1 = login_as(client, admin, "admin_1", "9000000961")
    a2 = login_as(client, admin, "admin_2", "9000000962")

    # Super Admin and Admin-1 can register and edit.
    g = ok(client.post(f"{API}/external-girls", headers=admin, json={"name": "Access Girl One"}), 201)
    g2 = ok(client.post(f"{API}/external-girls", headers=a1, json={"name": "Access Girl Two"}), 201)
    ok(client.patch(f"{API}/external-girls/{g['id']}", headers=a1, json={"location": "Palam"}))
    call = ok(client.post(f"{API}/external-calls", headers=a1, json={"external_girl_id": g2["id"], "purpose": "follow_up"}), 201)

    # Admin-2 can read everything but change nothing.
    ok(client.get(f"{API}/external-girls", headers=a2))
    ok(client.get(f"{API}/external-girls/{g['id']}", headers=a2))
    ok(client.get(f"{API}/external-calls", headers=a2))
    assert client.post(f"{API}/external-girls", headers=a2, json={"name": "Blocked Girl"}).status_code == 403
    assert client.patch(f"{API}/external-girls/{g['id']}", headers=a2, json={"location": "x"}).status_code == 403
    assert client.post(f"{API}/external-calls", headers=a2, json={"external_girl_id": g["id"], "purpose": "follow_up"}).status_code == 403
    assert client.patch(f"{API}/external-calls/{call['id']}", headers=a2, json={"notes": "x"}).status_code == 403


def test_media_library_roles_and_filters(client, admin, mongo):
    a1 = login_as(client, admin, "admin_1", "9000000963")
    a2 = login_as(client, admin, "admin_2", "9000000964")
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "Media Taluka", "name_mr": "म", "district": "Parbhani"}), 201)
    v1 = ok(client.post(f"{API}/villages", headers=admin, json={"name": "Media Village One", "name_mr": "गाव१", "taluka_id": t["id"]}), 201)
    v2 = ok(client.post(f"{API}/villages", headers=admin, json={"name": "Media Village Two", "name_mr": "गाव२", "taluka_id": t["id"]}), 201)
    now = datetime.now(UTC)
    event = lambda title, vid: ObjectId(ok(client.post(f"{API}/events", headers=admin, json={
        "title": title, "event_type": "kishori_meeting", "village_id": vid,
        "event_date": (date.today() + timedelta(days=5)).isoformat()}), 201)["id"])
    ev1, ev2 = event("Media Event One", v1["id"]), event("Media Event Two", v2["id"])
    old = now - timedelta(days=40)
    m_new = mongo.media.insert_one({"entity_type": "event", "entity_id": ev1, "content_type": "image/jpeg",
                                    "original_name": "new.jpg", "uploaded_at": now, "sensitive": False}).inserted_id
    m_old = mongo.media.insert_one({"entity_type": "event", "entity_id": ev2, "content_type": "image/jpeg",
                                    "original_name": "old.jpg", "uploaded_at": old, "sensitive": False}).inserted_id

    # Admin-2 and volunteers have no access.
    assert client.get(f"{API}/media/library", headers=a2).status_code == 403

    lib = ok(client.get(f"{API}/media/library", headers=a1, params={"page_size": 500}))
    ids = [i["id"] for i in lib["items"]]
    assert ids.index(str(m_new)) < ids.index(str(m_old))  # newest first
    row = next(i for i in lib["items"] if i["id"] == str(m_new))
    assert row["village_name"] == "Media Village One" and row["entity_label"] == "Media Event One"

    by_village = ok(client.get(f"{API}/media/library", headers=admin, params={"village_id": v2["id"]}))
    assert [i["id"] for i in by_village["items"]] == [str(m_old)]

    since = (date.today() - timedelta(days=7)).isoformat()
    recent = ok(client.get(f"{API}/media/library", headers=admin, params={"start_date": since, "page_size": 500}))
    recent_ids = {i["id"] for i in recent["items"]}
    assert str(m_new) in recent_ids and str(m_old) not in recent_ids
