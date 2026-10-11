"""Report templates, SMS participant reminders, push subscriptions, sync status, village locations."""

from datetime import date, timedelta

API = "/api/v1"
X: dict = {}
TODAY = date.today()


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def test_setup(client, admin):
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "Gangakhed", "district": "Parbhani"}), 201)
    v = ok(client.post(f"{API}/villages", headers=admin, json={"name": "Isaad", "name_mr": "इसाद", "taluka_id": t["id"]}), 201)
    g = ok(client.post(f"{API}/groups", headers=admin, json={"name": "स्वराज", "village_id": v["id"]}), 201)
    X.update(taluka=t["id"], village=v["id"], group=g["id"])
    for name, phone in (("Asha Kale", "9811111111"), ("Usha Kale", "9811111111"), ("Rupa Jadhav", None)):
        body = {"name": name, "village_id": v["id"], "group_id": g["id"], "age": 15, "confirm_not_duplicate": True}
        if phone:
            body["household"] = {"phone": phone}
        ok(client.post(f"{API}/girls", headers=admin, json=body), 201)


def test_report_templates(client, admin):
    st = ok(client.get(f"{API}/reports/types/village_wise/structure", headers=admin))
    assert st["sections"][0]["key"] == "village_wise"
    bad = client.post(f"{API}/reports/templates", headers=admin, json={
        "name": "Bad", "report_type": "village_wise", "sections": [{"key": "village_wise", "columns": ["nope"]}]})
    assert bad.status_code == 422 and "nope" in bad.text
    tpl = ok(client.post(f"{API}/reports/templates", headers=admin, json={
        "name": "Gangakhed donor brief", "report_type": "village_wise", "default_period": "yearly",
        "taluka_id": X["taluka"], "title": "Gangakhed outreach", "subtitle_note": "For donor review",
        "sections": [{"key": "village_wise", "title": "Villages", "columns": ["village", "girls", "home_visits"]}],
        "notes": ["Prepared by SEDT"]}), 201)
    X["tpl"] = tpl["id"]
    assert client.post(f"{API}/reports/templates", headers=admin, json={
        "name": "Gangakhed donor brief", "report_type": "village_wise"}).status_code == 409
    rep = ok(client.get(f"{API}/reports/templates/{tpl['id']}/run", headers=admin))
    assert rep["title"] == "Gangakhed outreach" and rep["period"]["type"] == "yearly"
    sec = rep["sections"][0]
    assert sec["title"] == "Villages" and [c["key"] for c in sec["columns"]] == ["village", "girls", "home_visits"]
    assert [r["village"] for r in sec["rows"]] == ["Isaad"]  # scoped to the template's taluka
    assert rep["notes"][0] == "Prepared by SEDT" and "For donor review" in rep["subtitle"]
    pdf = client.get(f"{API}/reports/templates/{tpl['id']}/run", headers=admin, params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    me = ok(client.get(f"{API}/auth/me", headers=admin))
    shared = ok(client.post(f"{API}/reports/templates/{tpl['id']}/share", headers=admin, json={"recipient_user_ids": [me["id"]]}))
    assert shared["template_id"] == tpl["id"]
    sch = ok(client.post(f"{API}/reports/schedules", headers=admin, json={
        "name": "Weekly template", "template_id": tpl["id"], "frequency": "weekly", "recipient_user_ids": [me["id"]]}), 201)
    assert sch["report_type"] == "village_wise"
    assert client.post(f"{API}/reports/schedules", headers=admin, json={
        "name": "Both", "template_id": tpl["id"], "report_type": "health", "frequency": "weekly",
        "recipient_user_ids": [me["id"]]}).status_code == 422
    run = ok(client.post(f"{API}/reports/schedules/{sch['id']}/run-now", headers=admin))
    assert run["template_id"] == tpl["id"] and run["title"] == "Gangakhed outreach"
    assert client.delete(f"{API}/reports/templates/{tpl['id']}", headers=admin).status_code == 409  # in use
    ok(client.patch(f"{API}/reports/schedules/{sch['id']}", headers=admin, json={"is_active": False}))
    assert client.delete(f"{API}/reports/templates/{tpl['id']}", headers=admin).status_code == 204
    assert ok(client.get(f"{API}/reports/templates", headers=admin)) == []


def test_participant_sms(client, admin):
    ev = ok(client.post(f"{API}/events", headers=admin, json={
        "title": "आरोग्य शिबिर", "event_type": "health_camp", "village_id": X["village"],
        "event_date": str(TODAY + timedelta(days=1)), "group_ids": [X["group"]], "notify_participants": True}), 201)
    assert ev["notify_participants"] is True
    # no provider configured -> recorded as skipped, never silently lost
    res = ok(client.post(f"{API}/events/{ev['id']}/notify-participants", headers=admin))
    assert res["skipped"] == 1 and res["no_phone"] == 1
    out = ok(client.get(f"{API}/messages", headers=admin))
    assert out["items"][0]["error"] == "No active SMS provider configured"

    ok(client.put(f"{API}/config/providers", headers=admin, json={
        "provider_type": "sms", "provider_name": "console", "is_active": True, "is_default": True}))
    ev2 = ok(client.post(f"{API}/events", headers=admin, json={
        "title": "Kishori meeting", "event_type": "kishori_meeting", "village_id": X["village"],
        "event_date": str(TODAY + timedelta(days=1)), "start_time": "11:00", "group_ids": [X["group"]],
        "notify_participants": True, "location_name": "ZP School"}), 201)
    res = ok(client.post(f"{API}/events/{ev2['id']}/notify-participants", headers=admin))
    assert res["logged"] == 1  # two sisters share one phone -> one message
    again = ok(client.post(f"{API}/events/{ev2['id']}/notify-participants", headers=admin))
    assert again["duplicate"] == 1 and again["logged"] == 0
    msg = ok(client.get(f"{API}/messages", headers=admin, params={"status": "logged"}))["items"][0]
    assert msg["to"] == "9811111111" and "ZP School" in msg["body"] and "11:00" in msg["body"]
    # scheduler sends tomorrow's reminders, but never twice
    checks = ok(client.post(f"{API}/notifications/run-checks", headers=admin))
    assert checks["volunteer_reminders"] >= 0
    assert ok(client.get(f"{API}/messages", headers=admin, params={"status": "logged"}))["total"] == 1 + 1  # ev + ev2
    bad_tpl = client.put(f"{API}/config/settings/messaging", headers=admin, json={
        "participant_reminders_enabled": True, "participant_reminder_template": "Hello {name}, see you"})
    assert bad_tpl.status_code == 422
    sms = ok(client.post(f"{API}/messages/test-sms", headers=admin, json={"to": "9822222222", "body": "Test"}))
    assert sms["status"] == "logged"


def test_push_and_sync(client, admin):
    assert client.get(f"{API}/push/public-key", headers=admin).status_code == 503  # VAPID not configured in tests
    sub = ok(client.post(f"{API}/push/subscriptions", headers=admin, json={
        "endpoint": "https://push.example.com/abc", "keys": {"p256dh": "k", "auth": "a"}}), 201)
    assert sub["devices"] == 1
    assert client.delete(f"{API}/push/subscriptions", headers=admin,
                         params={"endpoint": "https://push.example.com/abc"}).status_code == 204

    r = ok(client.post(f"{API}/sync/status", headers=admin, json={"device_id": "phone-1", "pending": 3, "failed": 2,
                                                               "errors": ["Photo too large"]}))
    assert r["state"] == "failed"
    notes = ok(client.get(f"{API}/notifications", headers=admin, params={"type": "sync_failed"}))
    assert notes["total"] == 1 and notes["items"][0]["message"] == "Photo too large"
    r = ok(client.post(f"{API}/sync/status", headers=admin, json={"device_id": "phone-1", "synced_in_batch": 5}))
    assert r == {"state": "synced", "previous_state": "failed"}
    assert ok(client.get(f"{API}/notifications", headers=admin, params={"type": "sync_complete"}))["total"] == 1
    overview = ok(client.get(f"{API}/sync/status", headers=admin))
    assert overview["counts"]["total"] == 1 and overview["devices"][0]["state"] == "synced"


def test_village_locations(client, admin):
    ok(client.put(f"{API}/villages/locations", headers=admin, json={
        "items": [{"village_id": X["village"], "lat": 18.97, "lng": 76.75, "pin_code": "431514"}]}))
    v = ok(client.get(f"{API}/villages/{X['village']}", headers=admin))
    assert v["location"] == {"lat": 18.97, "lng": 76.75} and v["pin_code"] == "431514"
    assert client.put(f"{API}/villages/locations", headers=admin, json={
        "items": [{"village_id": "0" * 24, "lat": 1, "lng": 1}]}).status_code == 404
    mapped = ok(client.get(f"{API}/dashboard/villages", headers=admin))
    assert "Isaad" not in mapped["unmapped"]
