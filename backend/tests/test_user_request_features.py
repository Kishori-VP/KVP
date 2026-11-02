"""Tests for the three user requested features:
1. Balpanchayat member name cleaning and gender assignment
2. Auto-scheduled monthly meetings for all Balpanchayat and Kishori groups
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


def test_auto_schedule_monthly_meetings_api(client, admin):
    # Trigger auto-schedule monthly meetings endpoint
    res = ok(client.post(f"{API}/events/auto-schedule-monthly", headers=admin, params={"year": 2026, "month": 11}))
    assert "created" in res
    assert res["year"] == 2026
    assert res["month"] == 11

    # Idempotent re-run
    res2 = ok(client.post(f"{API}/events/auto-schedule-monthly", headers=admin, params={"year": 2026, "month": 11}))
    assert res2["created"] == 0


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
