"""End-to-end Stakeholder (admin) flow against a real MongoDB test database.

Tests run in order and share state (ids) through the module-level `S` dict.
"""

import io
import zipfile
from datetime import date, timedelta

import pytest
from pymongo.errors import DuplicateKeyError

API = "/api/v1"
S: dict = {}
TODAY = date.today()


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def test_auth(client, admin):
    me = ok(client.get(f"{API}/auth/me", headers=admin))
    assert me["role"] == "stakeholder"
    assert "password_hash" not in me
    assert client.post(f"{API}/auth/login", json={"identifier": "9000000001", "password": "wrong"}).status_code == 401
    assert client.get(f"{API}/users").status_code == 401


def test_master_data(client, admin):
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "Palam", "name_mr": "पालम", "district": "Parbhani"}), 201)
    S["taluka"] = t["id"]
    v1 = ok(client.post(f"{API}/villages", headers=admin, json={
        "name": "Banwas", "name_mr": "बनवस", "taluka_id": t["id"], "location": {"lat": 19.0, "lng": 76.9}}), 201)
    v2 = ok(client.post(f"{API}/villages", headers=admin, json={"name": "Chatori", "name_mr": "चाटोरी", "taluka_id": t["id"]}), 201)
    S["v1"], S["v2"] = v1["id"], v2["id"]
    assert client.post(f"{API}/villages", headers=admin, json={"name": "Banwas", "taluka_id": t["id"]}).status_code == 409
    g1 = ok(client.post(f"{API}/groups", headers=admin, json={"name": "सावित्रीबाई फुले", "village_id": v1["id"]}), 201)
    g2 = ok(client.post(f"{API}/groups", headers=admin, json={"name": "हिरकणी", "village_id": v1["id"]}), 201)
    g3 = ok(client.post(f"{API}/groups", headers=admin, json={"name": "ताराराणी", "village_id": v2["id"]}), 201)
    ok(client.post(f"{API}/groups", headers=admin, json={"name": "स्वराज गट", "group_type": "bal_panchayat", "village_id": v1["id"]}), 201)
    S["g1"], S["g2"], S["g3"] = g1["id"], g2["id"], g3["id"]
    villages = ok(client.get(f"{API}/villages", headers=admin))
    banwas = next(v for v in villages if v["name"] == "Banwas")
    assert banwas["kishori_group_count"] == 2
    detail = ok(client.get(f"{API}/villages/{v1['id']}", headers=admin))
    assert set(detail["missing_mandatory_contacts"]) == {"hospital_head", "police_patil", "sarpanch", "talathi"}
    assert ok(client.get(f"{API}/districts", headers=admin))[0]["district"] == "Parbhani"


def test_one_village_per_volunteer(client, admin, mongo):
    # A volunteer can be created without a village and assigned later (at most one village at a time).
    later = ok(client.post(f"{API}/users", headers=admin, json={
        "name": "Sulochana", "phone": "9000000014", "password": "volunteer-3", "role": "volunteer"}), 201)
    assert later["village_id"] is None
    unassigned = ok(client.get(f"{API}/volunteers", headers=admin, params={"assigned": False}))
    assert [v["id"] for v in unassigned] == [later["id"]]
    assert client.post(f"{API}/users", headers=admin, json={
        "name": "X", "phone": "9000000015", "password": "volunteer-x", "role": "volunteer",
        "group_ids": [S["g1"]]}).status_code == 422  # groups need a village
    assigned = ok(client.post(f"{API}/volunteers/{later['id']}/assign", headers=admin, json={"village_id": S["v2"]}))
    assert assigned["volunteer"]["village_id"] == S["v2"]
    assert client.post(f"{API}/volunteers/{later['id']}/assign", headers=admin,
                       json={"village_id": S["v1"]}).status_code == 409  # already has a village
    ok(client.patch(f"{API}/users/{later['id']}/status", headers=admin, json={"is_active": False}))

    base = {"name": "Pooja Paul", "phone": "9000000011", "password": "volunteer-1", "role": "volunteer"}
    # groups from another village are rejected
    r = client.post(f"{API}/users", headers=admin, json={**base, "village_id": S["v1"], "group_ids": [S["g3"]]})
    assert r.status_code == 422
    vol = ok(client.post(f"{API}/users", headers=admin, json={**base, "village_id": S["v1"], "group_ids": [S["g1"]]}), 201)
    S["vol"] = vol["id"]
    assert vol["village_id"] == S["v1"] and vol["group_ids"] == [S["g1"]]
    assert client.post(f"{API}/users", headers=admin, json={**base, "village_id": S["v1"]}).status_code == 409
    vol2 = ok(client.post(f"{API}/users", headers=admin, json={
        "name": "Manisha", "phone": "9000000012", "password": "volunteer-2", "role": "volunteer", "village_id": S["v2"]}), 201)
    S["vol2"] = vol2["id"]
    # database-level guarantee: a second current assignment for the same volunteer is impossible
    from bson import ObjectId
    with pytest.raises(DuplicateKeyError):
        mongo.volunteer_assignments.insert_one({"volunteer_id": ObjectId(S["vol"]), "village_id": ObjectId(S["v2"]),
                                                "is_current": True})
    # stakeholders cannot be mapped to a village
    r = client.post(f"{API}/users", headers=admin, json={"name": "X", "phone": "9000000013", "password": "xxxxxxxx",
                                                         "role": "stakeholder", "village_id": S["v1"]})
    assert r.status_code == 422


def test_volunteer_cannot_use_admin_api(client):
    r = ok(client.post(f"{API}/auth/login", json={"identifier": "9000000011", "password": "volunteer-1"}))
    vh = {"Authorization": f"Bearer {r['access_token']}"}
    S["vol_headers"] = vh
    assert client.get(f"{API}/users", headers=vh).status_code == 403
    assert client.get(f"{API}/dashboard/summary", headers=vh).status_code == 403
    assert client.put(f"{API}/config/settings/girl_id", headers=vh, json={"prefix": "X", "pad": 0}).status_code == 403
    # village-scoped read: volunteer only sees own village
    assert [v["id"] for v in ok(client.get(f"{API}/villages", headers=vh))] == [S["v1"]]


def test_contacts(client, admin):
    c1 = ok(client.post(f"{API}/contacts", headers=admin, json={
        "village_id": S["v1"], "category": "sarpanch", "name": "Ramesh Patil", "mobile": "9876543210"}), 201)
    assert c1["quick_actions"]["call"] == "tel:+919876543210"
    r = client.post(f"{API}/contacts", headers=admin, json={
        "village_id": S["v1"], "category": "sarpanch", "name": "Another", "mobile": "9876543211"})
    assert r.status_code == 409  # one active Sarpanch per village
    assert client.post(f"{API}/contacts", headers=admin, json={
        "village_id": S["v1"], "category": "talathi", "name": "Bad Mobile", "mobile": "12345"}).status_code == 422
    v = ok(client.post(f"{API}/contacts/{c1['id']}/verify", headers=admin))
    assert v["verified"] is True
    edited = ok(client.patch(f"{API}/contacts/{c1['id']}", headers=admin, json={"mobile": "9876500000"}))
    assert edited["verified"] is False  # changing details resets verification
    cov = ok(client.get(f"{API}/contacts/coverage", headers=admin))
    assert cov["villages_total"] == 2 and cov["villages_complete"] == 0


def test_girls_and_duplicates(client, admin):
    body = {"name": "पूजा राजू शिंदे", "village_id": S["v1"], "group_id": S["g1"], "age": 14, "school_status": "studying",
            "household": {"father_name": "राजू शिंदे", "mother_name": "सुनीता"}}
    # Girls are registered by the Volunteer of that village; Stakeholders are read-only here.
    assert client.post(f"{API}/girls", headers=admin, json=body).status_code == 403
    vh = S["vol_headers"]
    g = ok(client.post(f"{API}/girls", headers=vh, json=body), 201)
    S["girl"] = g["id"]
    assert g["girl_code"].startswith("KVP-2627-") and g["age_band"] == "10_14"
    r = client.post(f"{API}/girls", headers=vh, json={**body, "name": "पूजा राजु शिंदे"})
    assert r.status_code == 409 and r.json()["detail"]["candidates"]
    g2 = ok(client.post(f"{API}/girls", headers=vh, json={**body, "name": "पूजा राजु शिंदे", "confirm_not_duplicate": True}), 201)
    S["girl_dup"] = g2["id"]
    # A volunteer cannot register a girl outside their own village.
    assert client.post(f"{API}/girls", headers=vh, json={"name": "Kavita More", "village_id": S["v2"], "age": 17}).status_code in (403, 422)
    r2 = ok(client.post(f"{API}/auth/login", json={"identifier": "9000000012", "password": "volunteer-2"}))
    ok(client.post(f"{API}/girls", headers={"Authorization": f"Bearer {r2['access_token']}"},
                   json={"name": "Kavita More", "village_id": S["v2"], "age": 17}), 201)
    assert client.post(f"{API}/girls", headers=vh, json={**body, "group_id": S["g3"], "name": "Other"}).status_code == 422
    assert client.post(f"{API}/girls", headers=vh, json={**body, "school_status": "nope", "name": "Zed"}).status_code == 422

    lst = ok(client.get(f"{API}/girls", headers=admin, params={"village_id": S["v1"], "age_band": "10_14"}))
    assert lst["total"] == 2
    assert ok(client.get(f"{API}/girls", headers=admin, params={"q": "Kavita"}))["total"] == 1
    assert ok(client.get(f"{API}/girls", headers=admin, params={"taluka_id": S["taluka"]}))["total"] == 3
    scan = ok(client.get(f"{API}/girls/duplicates", headers=admin, params={"village_id": S["v1"]}))
    assert scan["total_pairs"] == 1
    merged = ok(client.post(f"{API}/girls/{S['girl']}/merge", headers=admin, json={"duplicate_id": S["girl_dup"], "reason": "Same girl"}))
    assert merged["id"] == S["girl"]
    assert ok(client.get(f"{API}/girls", headers=admin, params={"village_id": S["v1"]}))["total"] == 1


def test_girl_aadhaar_images(client, admin):
    def upload(content, kind, entity_type="girl"):
        return client.post(f"{API}/media", headers=admin, files={"file": ("aadhaar.png", content, "image/png")},
                           data={"entity_type": entity_type, "entity_id": S["girl"], "kind": kind})

    front = ok(upload(b"\x89PNG front-1", "aadhaar_front"), 201)
    assert front["kind"] == "aadhaar_front" and front["sensitive"] is True
    ok(upload(b"\x89PNG back", "aadhaar_back"), 201)
    assert upload(b"\x89PNG back", "aadhaar_front").status_code == 409
    new_front = ok(upload(b"\x89PNG front-2", "aadhaar_front"), 201)
    media = ok(client.get(f"{API}/media", headers=admin, params={"entity_type": "girl", "entity_id": S["girl"]}))
    assert sorted(m["kind"] for m in media) == ["aadhaar_back", "aadhaar_front"]
    assert new_front["id"] in {m["id"] for m in media} and front["id"] not in {m["id"] for m in media}
    assert upload(b"\x89PNG x", "aadhaar_front", entity_type="case").status_code == 422


def test_health_and_cases(client, admin):
    h = ok(client.post(f"{API}/girls/{S['girl']}/health", headers=admin, json={
        "recorded_on": str(TODAY), "hb_level": 10.2, "weight_kg": 38, "height_cm": 150,
        "observations": {"ifa_tablets": True, "hb_test_method": "digital"}, "source": "health_camp"}), 201)
    assert h["anaemia_status"] == "moderate" and h["bmi"] == 16.9
    assert client.post(f"{API}/girls/{S['girl']}/health", headers=admin, json={
        "recorded_on": str(TODAY), "observations": {"unknown_field": 1}}).status_code == 422
    assert ok(client.get(f"{API}/girls", headers=admin, params={"anaemia": "moderate"}))["total"] == 1

    case = ok(client.post(f"{API}/cases", headers=admin, json={
        "girl_id": S["girl"], "category": "child_marriage_risk", "severity": "high",
        "title": "Family discussing marriage", "assigned_to": S["vol"]}), 201)
    S["case"] = case["id"]
    assert case["case_code"].startswith("CASE-") and case["due_date"]
    assert client.post(f"{API}/cases", headers=admin, json={
        "girl_id": S["girl"], "category": "x", "severity": "high", "title": "bad"}).status_code == 422
    assert client.post(f"{API}/cases", headers=admin, json={
        "girl_id": S["girl"], "category": "school_dropout", "severity": "low", "title": "wrong village assignee",
        "assigned_to": S["vol2"]}).status_code == 422
    ok(client.post(f"{API}/cases/{case['id']}/notes", headers=admin, json={"type": "follow_up", "text": "Met parents"}))
    assert client.post(f"{API}/cases/{case['id']}/status", headers=admin, json={"status": "open", "note": "x"}).status_code == 422
    ok(client.post(f"{API}/cases/{case['id']}/status", headers=admin, json={"status": "escalated", "note": "Needs PC visit"}))
    girl = ok(client.get(f"{API}/girls/{S['girl']}", headers=admin))
    assert girl["case_summary"]["open"] == 1 and girl["health_summary"]["anaemia_status"] == "moderate"
    assert ok(client.get(f"{API}/girls", headers=admin, params={"case_status": "open"}))["total"] == 1
    ok(client.post(f"{API}/cases/{case['id']}/status", headers=admin, json={"status": "resolved", "note": "Family counselled"}))
    assert ok(client.get(f"{API}/girls/{S['girl']}/cases", headers=admin))["cases"][0]["status"] == "resolved"


def test_events(client, admin):
    future = ok(client.post(f"{API}/events", headers=admin, json={
        "title": "Health camp Banwas", "event_type": "health_camp", "village_id": S["v1"],
        "event_date": str(TODAY + timedelta(days=5)), "start_time": "10:00", "end_time": "13:00",
        "responsible_volunteer_id": S["vol"], "expected_participants": 40, "group_ids": [S["g1"]]}), 201)
    S["event_future"] = future["id"]
    assert future["display_status"] == "upcoming" and len(future["pre_checklist"]) == 5
    assert client.put(f"{API}/events/{future['id']}/attendance", headers=admin,
                      json={"entries": [{"girl_id": S["girl"]}]}).status_code == 422
    assert client.post(f"{API}/events", headers=admin, json={
        "title": "Past event", "event_type": "health_camp", "village_id": S["v1"],
        "event_date": str(TODAY - timedelta(days=3))}).status_code == 422
    assert client.post(f"{API}/events", headers=admin, json={
        "title": "Wrong volunteer", "event_type": "health_camp", "village_id": S["v1"],
        "event_date": str(TODAY + timedelta(days=1)), "responsible_volunteer_id": S["vol2"]}).status_code == 422

    past = ok(client.post(f"{API}/events", headers=admin, json={
        "title": "Kishori meeting", "event_type": "kishori_meeting", "village_id": S["v1"],
        "event_date": str(TODAY - timedelta(days=2)), "is_historical": True,
        "responsible_volunteer_id": S["vol"], "expected_participants": 15, "group_ids": [S["g1"]]}), 201)
    S["event_past"] = past["id"]
    assert past["display_status"] == "overdue"
    ev = ok(client.put(f"{API}/events/{past['id']}/attendance", headers=admin, json={
        "mark_groups_present": [S["g1"]], "other_participants": {"parents": 3}}))
    assert ev["attendance_summary"]["girls_present"] == 1 and ev["attendance_summary"]["total_present"] == 4
    ok(client.put(f"{API}/events/{past['id']}/checklists/pre", headers=admin, json={"items": [{"item": "Venue confirmed", "done": True}]}))
    ok(client.put(f"{API}/events/{past['id']}/expenditure", headers=admin, json={
        "items": [{"item": "Snacks", "category": "refreshments", "quantity": 20, "unit_cost": 15}]}))
    done = ok(client.post(f"{API}/events/{past['id']}/report", headers=admin, json={
        "activities_conducted": "बालविवाह कायद्याबद्दल माहिती दिली", "outcomes": "Girls understood the law",
        "follow_up_actions": "Visit 2 families"}))
    assert done["display_status"] == "completed" and done["expenditure"]["total"] == 300.0

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    m1 = ok(client.post(f"{API}/events/{past['id']}/media", headers=admin, files={"file": ("a.png", png, "image/png")},
                        data={"lat": "19.01", "lng": "76.91"}), 201)
    m2 = ok(client.post(f"{API}/events/{past['id']}/media", headers=admin, files={"file": ("b.png", png, "image/png")}), 201)
    assert m2["duplicate"] is True and m1["id"] == m2["id"]
    assert client.get(f"{API}/media/{m1['id']}/file", headers=admin).content == png

    cal = ok(client.get(f"{API}/events/calendar", headers=admin, params={
        "start_date": str(TODAY - timedelta(days=7)), "end_date": str(TODAY + timedelta(days=7))}))
    assert cal["counts"] == {"completed": 1, "upcoming": 1}
    pvc = ok(client.get(f"{API}/events/planned-vs-conducted", headers=admin, params={
        "start_date": str(TODAY - timedelta(days=30)), "end_date": str(TODAY + timedelta(days=30))}))
    assert pvc["totals"]["planned"] == 1 and pvc["totals"]["unplanned_conducted"] == 1
    pdf = client.get(f"{API}/events/{past['id']}/export", headers=admin, params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    xlsx = client.get(f"{API}/events/{past['id']}/export", headers=admin, params={"format": "xlsx"})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    ok(client.post(f"{API}/events/{future['id']}/cancel", headers=admin, json={"reason": "Rain"}))
    assert client.put(f"{API}/events/{future['id']}/attendance", headers=admin, json={"entries": []}).status_code == 409


def test_field_records_and_targets(client, admin):
    ok(client.post(f"{API}/home-visits", headers=admin, json={
        "volunteer_id": S["vol"], "visit_date": str(TODAY), "girl_ids": [S["girl"]], "purpose": "follow_up",
        "risk_indicators": {"child_marriage_risk": True}}), 201)
    ok(client.post(f"{API}/home-visits", headers=admin, json={
        "volunteer_id": S["vol"], "visit_date": str(TODAY + timedelta(days=2)), "status": "planned"}), 201)
    assert client.post(f"{API}/home-visits", headers=admin, json={
        "volunteer_id": S["vol"], "visit_date": str(TODAY + timedelta(days=2)), "status": "completed"}).status_code == 422
    ok(client.post(f"{API}/activity-reports", headers=admin, json={
        "volunteer_id": S["vol"], "report_date": str(TODAY - timedelta(days=1)),
        "activities": ["kishori_group_meeting", "home_visit"], "group_ids": [S["g1"]], "girls_present": 12,
        "home_visits_count": 4}), 201)
    assert client.post(f"{API}/activity-reports", headers=admin, json={
        "volunteer_id": S["vol"], "report_date": str(TODAY - timedelta(days=1)), "activities": []}).status_code == 409

    res = ok(client.post(f"{API}/targets", headers=admin, json={
        "volunteer_ids": [S["vol"]], "target_type": "home_visits", "period_type": "monthly",
        "target_value": 10, "periods": 2}), 201)
    assert len(res["created"]) == 2
    S["target"] = res["created"][0]["id"]
    again = ok(client.post(f"{API}/targets", headers=admin, json={
        "volunteer_ids": [S["vol"]], "target_type": "home_visits", "period_type": "monthly", "target_value": 5}), 201)
    assert len(again["created"]) == 0 and len(again["skipped"]) == 1
    t = ok(client.get(f"{API}/targets/{S['target']}", headers=admin))
    # 1 structured visit today + 4 from yesterday's daily report (no structured visit that day)
    assert t["progress"]["achieved"] == 5
    assert t["progress"]["status"] in ("on_track", "at_risk", "achieved")
    rev = ok(client.patch(f"{API}/targets/{S['target']}", headers=admin, json={"target_value": 5, "reason": "Monsoon"}))
    assert rev["progress"]["status"] == "achieved" and rev["revisions"][0]["reason"] == "Monsoon"
    lst = ok(client.get(f"{API}/targets", headers=admin, params={"when": "upcoming"}))
    assert lst["total"] == 1 and lst["items"][0]["progress"]["status"] == "upcoming"


def test_reassignment_moves_targets(client, admin):
    r = ok(client.post(f"{API}/volunteers/{S['vol']}/reassign", headers=admin, json={
        "village_id": S["v2"], "group_ids": [S["g3"]], "reason": "Field restructuring", "targets": {"action": "move"}}))
    assert r["volunteer"]["village_id"] == S["v2"] and r["targets"]["affected"] == 2
    hist = ok(client.get(f"{API}/volunteers/{S['vol']}/assignments", headers=admin))
    assert len(hist) == 2 and sum(h["is_current"] for h in hist) == 1
    assert hist[1]["end_date"] is not None
    g1 = ok(client.get(f"{API}/groups/{S['g1']}", headers=admin))
    assert g1["responsible_volunteer_id"] is None
    t = ok(client.get(f"{API}/targets/{S['target']}", headers=admin))
    assert t["village_id"] == S["v2"] and len(t["revisions"]) == 2
    assert client.post(f"{API}/volunteers/{S['vol']}/reassign", headers=admin, json={
        "village_id": S["v2"], "group_ids": [S["g3"]], "reason": "Same again"}).status_code == 409
    # move back so later tests see the original village
    ok(client.post(f"{API}/volunteers/{S['vol']}/reassign", headers=admin, json={
        "village_id": S["v1"], "group_ids": [S["g1"]], "reason": "Back to Banwas", "targets": {"action": "move"}}))


def test_volunteer_views(client, admin):
    dash = ok(client.get(f"{API}/volunteers/{S['vol']}/dashboard", headers=admin))
    assert dash["home_visits"]["this_month"] >= 1
    assert ok(client.get(f"{API}/volunteers/{S['vol']}/activity", headers=admin, params={"granularity": "weekly"}))["series"]
    assert ok(client.get(f"{API}/volunteers/{S['vol']}/history", headers=admin))
    cov = ok(client.get(f"{API}/volunteers/{S['vol']}/coverage", headers=admin))
    assert cov["girls"]["total"] == 1
    sub = ok(client.get(f"{API}/volunteers/submission-status", headers=admin))
    assert len(sub["volunteers"]) == 2
    perf = ok(client.get(f"{API}/volunteers/performance", headers=admin))
    assert any(v["target_count"] for v in perf["volunteers"])


def test_dashboard(client, admin):
    s = ok(client.get(f"{API}/dashboard/summary", headers=admin))
    assert s["girls_total"] == 2 and s["villages"] == 2 and s["kishori_groups"] == 3 and s["active_volunteers"] == 2
    assert s["events_conducted"] == 1
    for path in ("trends", "cases", "villages", "targets", "participation", "health", "alerts", "past-vs-upcoming"):
        ok(client.get(f"{API}/dashboard/{path}", headers=admin))
    assert ok(client.get(f"{API}/dashboard/villages", headers=admin))["counts"]["on_track"] >= 1
    for level, parent in (("district", None), ("taluka", "Parbhani"), ("village", S["taluka"]),
                          ("group", S["v1"]), ("volunteer", S["v1"]), ("girl", S["g1"])):
        rows = ok(client.get(f"{API}/dashboard/drilldown", headers=admin, params={"level": level, "parent_id": parent}))["rows"]
        assert rows, level


def test_reports(client, admin):
    types = ok(client.get(f"{API}/reports/types", headers=admin))["report_types"]
    for rt in types:
        rep = ok(client.get(f"{API}/reports/{rt}", headers=admin, params={"period": "monthly"}))
        assert rep["title"] and "sections" in rep, rt
    pdf = client.get(f"{API}/reports/donor_summary", headers=admin, params={"period": "yearly", "format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    xlsx = client.get(f"{API}/reports/village_wise", headers=admin, params={"period": "quarterly", "format": "xlsx"})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert client.get(f"{API}/reports/village_wise", headers=admin, params={"period": "custom"}).status_code == 422
    csv_ = client.get(f"{API}/reports/village_wise", headers=admin, params={"format": "csv"})
    assert csv_.status_code == 200 and csv_.content.startswith(b"\xef\xbb\xbf") and "Banwas" in csv_.content.decode("utf-8-sig")
    docx = client.get(f"{API}/reports/village_wise", headers=admin, params={"format": "docx"})
    assert docx.status_code == 200 and docx.content[:2] == b"PK" and docx.headers["content-disposition"].endswith('.docx"')
    bundle = client.get(f"{API}/reports/donor_summary", headers=admin, params={"formats": "pdf,xlsx,csv,docx"})
    assert bundle.status_code == 200 and bundle.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        assert sorted(n.rsplit(".", 1)[1] for n in zf.namelist()) == ["csv", "docx", "pdf", "xlsx"]
    single = client.get(f"{API}/reports/donor_summary", headers=admin, params={"formats": "csv"})
    assert single.headers["content-disposition"].endswith('.csv"')
    assert client.get(f"{API}/reports/donor_summary", headers=admin, params={"formats": "pdf,odt"}).status_code == 422
    me = ok(client.get(f"{API}/auth/me", headers=admin))
    multi = ok(client.post(f"{API}/reports/village_wise/share", headers=admin, json={
        "recipient_user_ids": [me["id"]], "formats": ["pdf", "csv", "docx"]}))
    assert sorted(f["format"] for f in multi["files"]) == ["csv", "docx", "pdf"]
    shared = ok(client.post(f"{API}/reports/programme_summary/share", headers=admin, json={
        "recipient_user_ids": [me["id"]], "formats": ["pdf"]}))
    assert shared["delivery"]["in_app"] == 1
    assert client.post(f"{API}/reports/programme_summary/share", headers=admin, json={
        "recipient_emails": ["stranger@example.com"]}).status_code == 422
    sch = ok(client.post(f"{API}/reports/schedules", headers=admin, json={
        "name": "Monthly donor", "report_type": "donor_summary", "frequency": "monthly", "recipient_user_ids": [me["id"]]}), 201)
    ok(client.post(f"{API}/reports/schedules/{sch['id']}/run-now", headers=admin))
    gen = ok(client.get(f"{API}/reports/generated", headers=admin))
    assert gen["total"] == 3
    dl = client.get(f"{API}/reports/generated/{gen['items'][0]['id']}/download", headers=admin, params={"format": "pdf"})
    assert dl.status_code == 200 and dl.content[:4] == b"%PDF"


def test_configuration(client, admin):
    assert ok(client.get(f"{API}/config/settings", headers=admin))["target_thresholds"]["on_track_min_ratio"] == 0.9
    bad = client.put(f"{API}/config/settings/anaemia_thresholds", headers=admin,
                     json={"severe_below": 12, "moderate_below": 11, "mild_below": 10})
    assert bad.status_code == 422
    ok(client.put(f"{API}/config/settings/village_status", headers=admin, json={"on_track_within_days": 10, "delayed_within_days": 30}))
    assert client.put(f"{API}/config/settings/permissions", headers=admin,
                      json={"volunteer": {"config": ["read"]}}).status_code == 422
    lk = ok(client.post(f"{API}/config/lookups", headers=admin, json={
        "type": "case_category", "code": "migration", "label": "Seasonal migration"}), 201)
    assert lk["code"] == "migration"
    assert client.post(f"{API}/config/lookups", headers=admin, json={
        "type": "target_type", "code": "bad_target", "label": "Bad"}).status_code == 422
    prov = ok(client.put(f"{API}/config/providers", headers=admin, json={
        "provider_type": "speech_to_text", "provider_name": "bhashini", "is_active": True,
        "config": {"language": "mr"}, "credentials": {"api_key": "super-secret-key-1234"}}))
    assert prov["credentials_masked"]["api_key"].endswith("1234") and "super-secret" not in str(prov)
    m = ok(client.get(f"{API}/config/permissions", headers=admin))
    assert "read" in m["matrix"]["volunteer"]["girls"] and m["matrix"]["volunteer"]["config"] == []
    logs = ok(client.get(f"{API}/audit-logs", headers=admin, params={"entity_type": "setting"}))
    assert logs["total"] >= 1


def test_audit_and_notifications(client, admin):
    logs = ok(client.get(f"{API}/audit-logs", headers=admin, params={"page_size": 200}))
    actions = {entry["action"] for entry in logs["items"]}
    assert {"create", "update", "reassign", "revise", "verify", "login", "status_change"} <= actions
    ok(client.post(f"{API}/notifications/run-checks", headers=admin))
    second = ok(client.post(f"{API}/notifications/run-checks", headers=admin))
    assert second["stakeholder_alerts"] == 0  # dedupe: nothing new on a second run
    sent = ok(client.post(f"{API}/notifications/announce", headers=admin, json={
        "title": "Monthly meeting", "message": "Meeting on Friday at Kerwadi office"}), 201)
    assert sent["sent"] == 2
    vol_notes = ok(client.get(f"{API}/notifications", headers=S["vol_headers"]))
    assert vol_notes["unread"] >= 1
