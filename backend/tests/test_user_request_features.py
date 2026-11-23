"""Tests for the three user requested features:
1. Balpanchayat member name cleaning and gender assignment
2. Monthly meeting planner for Balpanchayat and Kishori groups (replaces the auto-scheduler)
3. Home visit 6-month cooldown logic in /girls endpoint
"""

from datetime import date, timedelta
from bson import ObjectId
from app.utils.dates import six_months_ago, six_months_after, today_local, to_dt
from app.utils.gender import clean_child_name, infer_gender

API = "/api/v1"


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def test_gender_inference_and_name_cleaning():
    # Names with roles
    assert clean_child_name("यश वामन राष्ट्रकुट प्रमुख") == "यश वामन राष्ट्रकुट"
    assert clean_child_name("त्रिशा गजानन आष्टउ रकर") == "त्रिशा गजानन आष्टुरकर"

    # Gender classification
    assert infer_gender("राणी नागनाथ चवरे") == "girl"
    assert infer_gender("सोहम तुळशीराम घुमलवाड") == "boy"
    assert infer_gender("जोया हमजा शेख") == "girl"
    assert infer_gender("आसाद कलीम शेख") == "boy"
    assert infer_gender("रोहित ज्ञानोबा कुंभार") == "boy"
    assert infer_gender("रोहिणी ज्ञानोबा कुंभार") == "girl"


def test_child_create_and_gender(client, admin):
    # Create taluka, village, and a Bal Panchayat group
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "Palam BP", "name_mr": "पालम", "district": "Parbhani"}), 201)
    v = ok(client.post(f"{API}/villages", headers=admin, json={"name": "TestVillage BP", "name_mr": "गाव", "taluka_id": t["id"]}), 201)
    bp = ok(client.post(f"{API}/groups", headers=admin, json={"name": "बालपंचायत गट A", "group_type": "bal_panchayat", "village_id": v["id"]}), 201)

    # 1. Add child with female name without explicit gender -> inferred as girl
    c1 = ok(client.post(f"{API}/children", headers=admin, json={
        "group_id": bp["id"],
        "name": "राणी नागनाथ चवरे",
        "standard": "8"
    }), 201)
    assert c1["gender"] == "girl"

    # 2. Add child with male name without explicit gender -> inferred as boy
    c2 = ok(client.post(f"{API}/children", headers=admin, json={
        "group_id": bp["id"],
        "name": "सोहम तुळशीराम घुमलवाड",
        "standard": "8"
    }), 201)
    assert c2["gender"] == "boy"

    # 3. Add child with role suffix in name -> cleaned and inferred
    c3 = ok(client.post(f"{API}/children", headers=admin, json={
        "group_id": bp["id"],
        "name": "यश वामन राष्ट्रकुट प्रमुख",
        "standard": "7"
    }), 201)
    assert c3["name"] == "यश वामन राष्ट्रकुट"
    assert c3["gender"] == "boy"

    # 4. List children with gender filter
    all_children = ok(client.get(f"{API}/children", headers=admin, params={"group_id": bp["id"]}))
    assert all_children["total"] == 3

    girls_only = ok(client.get(f"{API}/children", headers=admin, params={"group_id": bp["id"], "gender": "girl"}))
    assert girls_only["total"] == 1
    assert girls_only["items"][0]["name"] == "राणी नागनाथ चवरे"

    boys_only = ok(client.get(f"{API}/children", headers=admin, params={"group_id": bp["id"], "gender": "boy"}))
    assert boys_only["total"] == 2


def test_suggested_meeting_date():
    from app.services.events import suggested_meeting_date
    assert suggested_meeting_date(None, 2026, 12) is None
    # 2nd Tuesday of December 2026 is the 8th
    assert suggested_meeting_date({"day_of_week": 1, "week_of_month": 2}, 2026, 12) == date(2026, 12, 8)
    # "5th Monday" falls back to the last Monday when the month has only four
    assert suggested_meeting_date({"day_of_week": 0, "week_of_month": 5}, 2026, 2) == date(2026, 2, 23)


def test_monthly_meeting_planner_api(client, admin):
    # The old one-click auto-scheduler is gone.
    assert client.post(f"{API}/events/auto-schedule-monthly", headers=admin).status_code in (404, 405)

    today = date.today()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "Planner Taluka", "name_mr": "प", "district": "Parbhani"}), 201)
    v = ok(client.post(f"{API}/villages", headers=admin, json={"name": "Planner Village", "name_mr": "गाव", "taluka_id": t["id"]}), 201)
    g = ok(client.post(f"{API}/groups", headers=admin, json={
        "name": "Planner Kishori", "village_id": v["id"],
        "meeting_schedule": {"frequency": "monthly", "day_of_week": 1, "week_of_month": 2, "time": "11:30"}}), 201)

    plan = ok(client.get(f"{API}/events/monthly-planner", headers=admin, params={"year": year, "month": month}))
    row = next(r for r in plan["groups"] if r["group_id"] == g["id"])
    assert row["event_type"] == "kishori_meeting" and row["suggested_time"] == "11:30"
    assert row["suggested_date"] and row["existing_event_id"] is None
    # Opening the planner creates nothing.
    assert ok(client.get(f"{API}/events/monthly-planner", headers=admin, params={"year": year, "month": month}))["already_planned"] == plan["already_planned"]

    body = {"year": year, "month": month, "meetings": [
        {"group_id": g["id"], "meeting_date": row["suggested_date"], "start_time": "11:30", "end_time": "13:00"}]}
    res = ok(client.post(f"{API}/events/monthly-planner", headers=admin, json=body))
    assert res["created"] == 1 and res["skipped"] == []
    ev = ok(client.get(f"{API}/events/{res['events'][0]['id']}", headers=admin))
    assert ev["event_type"] == "kishori_meeting" and ev["start_time"] == "11:30" and ev["planned"] is True

    # Same group again that month is skipped, and the planner shows it as planned.
    again = ok(client.post(f"{API}/events/monthly-planner", headers=admin, json=body))
    assert again["created"] == 0 and again["skipped"][0]["reason"] == "already planned"
    row = next(r for r in ok(client.get(f"{API}/events/monthly-planner", headers=admin,
                                        params={"year": year, "month": month}))["groups"] if r["group_id"] == g["id"])
    assert row["existing_event_id"] == res["events"][0]["id"]

    # Dates must be in the planned month and not in the past.
    bad_month = {**body, "meetings": [{**body["meetings"][0], "meeting_date": f"{year}-{month:02d}-01"}], "month": month % 12 + 1}
    assert client.post(f"{API}/events/monthly-planner", headers=admin, json=bad_month).status_code == 422
    past = {"year": today.year, "month": today.month, "meetings": [
        {"group_id": g["id"], "meeting_date": (today.replace(day=1) - timedelta(days=1)).isoformat()}]}
    assert client.post(f"{API}/events/monthly-planner", headers=admin, json=past).status_code == 422

    # Admin-2 (read-only) can view the planner but not create meetings.
    ok(client.post(f"{API}/users", headers=admin, json={
        "name": "Planner Admin Two", "phone": "9000000950", "password": "admin2-pass-1", "role": "admin_2"}), 201)
    tok = ok(client.post(f"{API}/auth/login", json={"identifier": "9000000950", "password": "admin2-pass-1"}))
    a2 = {"Authorization": f"Bearer {tok['access_token']}"}
    ok(client.get(f"{API}/events/monthly-planner", headers=a2))
    assert client.post(f"{API}/events/monthly-planner", headers=a2, json=body).status_code == 403


def test_group_tracked_meeting_stays_ongoing_until_all_groups_done(client, admin, mongo):
    from datetime import UTC, datetime
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "Track Taluka", "name_mr": "त", "district": "Parbhani"}), 201)
    v = ok(client.post(f"{API}/villages", headers=admin, json={"name": "Track Village", "name_mr": "गाव", "taluka_id": t["id"]}), 201)
    g1 = ok(client.post(f"{API}/groups", headers=admin, json={"name": "Track A", "village_id": v["id"]}), 201)
    g2 = ok(client.post(f"{API}/groups", headers=admin, json={"name": "Track B", "village_id": v["id"]}), 201)
    other = ok(client.post(f"{API}/groups", headers=admin, json={"name": "Elsewhere", "village_id": v["id"]}), 201)
    start = datetime.now(UTC) - timedelta(days=3)
    eid = mongo.events.insert_one({
        "title": "Track meeting", "event_type": "kishori_meeting", "village_id": ObjectId(v["id"]),
        "start_at": start, "end_at": start + timedelta(hours=2), "start_time": "16:00", "end_time": "18:00",
        "status": "scheduled", "planned": True, "track_groups": True, "groups_done": [],
        "group_ids": [ObjectId(g1["id"]), ObjectId(g2["id"])], "attendance": [], "other_participants": {},
        "expected_participants": 0, "pre_checklist": [], "post_checklist": [], "report": None,
        "expenditure": {"items": [], "total": 0}, "approval": {"status": "not_required"}, "reschedule_history": [],
    }).inserted_id
    url = f"{API}/events/{eid}"

    # Past its time but groups pending: ongoing, not overdue, and the report can't close it.
    assert ok(client.get(url, headers=admin))["display_status"] == "ongoing"
    ids = lambda st: {e["id"] for e in ok(client.get(f"{API}/events", headers=admin, params={"status": st}))["items"]}
    assert str(eid) in ids("ongoing") and str(eid) not in ids("overdue")
    assert client.post(f"{url}/report", headers=admin, json={"summary": "x"}).status_code == 422
    assert client.put(f"{url}/groups-done", headers=admin, json={"group_ids": [other["id"]]}).status_code == 422

    ev = ok(client.put(f"{url}/groups-done", headers=admin, json={"group_ids": [g1["id"]]}))
    assert ev["status"] == "scheduled" and ev["display_status"] == "ongoing" and len(ev["groups_done"]) == 1

    # Last group done: the meeting completes on its own.
    ev = ok(client.put(f"{url}/groups-done", headers=admin, json={"group_ids": [g1["id"], g2["id"]]}))
    assert ev["status"] == "completed"
    # Un-marking a group (no report yet) reopens it.
    assert ok(client.put(f"{url}/groups-done", headers=admin, json={"group_ids": [g2["id"]]}))["status"] == "scheduled"


def test_home_visit_cooldown_api(client, admin, mongo):
    # Create test girl
    t = ok(client.post(f"{API}/talukas", headers=admin, json={"name": "HV Taluka", "name_mr": "पालम", "district": "Parbhani"}), 201)
    v = ok(client.post(f"{API}/villages", headers=admin, json={"name": "HV Village", "name_mr": "गाव", "taluka_id": t["id"]}), 201)
    vol = ok(client.post(f"{API}/users", headers=admin, json={
        "name": "HV Volunteer", "phone": "9800000001", "password": "password123",
        "role": "volunteer", "village_ids": [v["id"]]
    }), 201)

    girl = ok(client.post(f"{API}/girls", headers=admin, json={
        "name": "कोमल गजानन पवार",
        "village_id": v["id"],
        "dob": "2010-01-01"
    }), 201)
    gid = girl["id"]

    # Before any home visit, girl is eligible for home visit
    girls_before = ok(client.get(f"{API}/girls", headers=admin, params={"village_id": v["id"], "for_home_visit": True}))
    found_before = [g for g in girls_before["items"] if g["id"] == gid]
    assert len(found_before) == 1

    # Complete a home visit today
    today = today_local().isoformat()
    visit = ok(client.post(f"{API}/home-visits", headers=admin, json={
        "volunteer_id": vol["id"],
        "village_id": v["id"],
        "visit_date": today,
        "girl_ids": [gid],
        "status": "completed",
        "purpose": "routine"
    }), 201)

    # Immediately after completed home visit, girl should disappear from /girls?for_home_visit=true
    girls_after = ok(client.get(f"{API}/girls", headers=admin, params={"village_id": v["id"], "for_home_visit": True}))
    found_after = [g for g in girls_after["items"] if g["id"] == gid]
    assert len(found_after) == 0, "Girl in 6-month cooldown should not appear in home visit dropdown!"

    # Still appears in regular /girls list (without for_home_visit=True)
    all_girls = ok(client.get(f"{API}/girls", headers=admin, params={"village_id": v["id"]}))
    found_all = [g for g in all_girls["items"] if g["id"] == gid]
    assert len(found_all) == 1
    assert found_all[0]["is_home_visit_eligible"] is False

    # Simulate 6 months passing by updating visit_date to 7 months ago
    old_dt = to_dt(today_local() - timedelta(days=210))
    mongo.home_visits.update_one({"_id": ObjectId(visit["id"])}, {"$set": {"visit_date": old_dt}})
    mongo.girls.update_one({"_id": ObjectId(gid)}, {"$set": {"last_home_visit_at": old_dt}})

    # Now she should automatically become eligible again and reappear in the dropdown!
    girls_expired = ok(client.get(f"{API}/girls", headers=admin, params={"village_id": v["id"], "for_home_visit": True}))
    found_expired = [g for g in girls_expired["items"] if g["id"] == gid]
    assert len(found_expired) == 1, "Girl should automatically reappear in dropdown after 6-month cooldown expires!"
    assert found_expired[0]["is_home_visit_eligible"] is True


def test_events_list_sorted_by_date_for_every_filter(client, admin):
    for status in (None, "upcoming", "today", "ongoing", "overdue", "completed", "cancelled"):
        params = {"page_size": 100, **({"status": status} if status else {})}
        starts = [e["start_at"] for e in ok(client.get(f"{API}/events", headers=admin, params=params))["items"]]
        assert starts == sorted(starts), status
