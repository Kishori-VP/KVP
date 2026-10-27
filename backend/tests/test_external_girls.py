"""Tests for External Girls and Call Logging (PRD - External Outreach)."""

from datetime import date
import pytest

API = "/api/v1"
TODAY = date.today().isoformat()


def test_external_girls_and_calls(client, admin):
    # 1. Register an external girl
    res = client.post(
        f"{API}/external-girls",
        headers=admin,
        json={
            "name": "पूजा देशमुख",
            "phone": "9876543210",
            "age": 16,
            "location": "परभणी शहर",
            "guardian_name": "संतोष देशमुख",
            "guardian_relation": "father",
            "education_status": "11th Science",
            "notes": "बाह्य विद्यार्थिनी, समुपदेशन आवश्यक",
        },
    )
    assert res.status_code == 201, res.text
    girl = res.json()
    assert girl["name"] == "पूजा देशमुख"
    assert girl["name_en"]  # auto-transliterated
    assert girl["phone"] == "9876543210"
    girl_id = girl["id"]

    # 2. List external girls
    res = client.get(f"{API}/external-girls", headers=admin)
    assert res.status_code == 200
    items = res.json()["items"]
    assert any(g["id"] == girl_id for g in items)

    # Search by phone or name
    res_search = client.get(f"{API}/external-girls?q=पूजा", headers=admin)
    assert res_search.status_code == 200
    assert any(g["id"] == girl_id for g in res_search.json()["items"])

    # 3. Log a call to the external girl
    res_call = client.post(
        f"{API}/external-calls",
        headers=admin,
        json={
            "external_girl_id": girl_id,
            "call_date": TODAY,
            "status": "completed",
            "purpose": "counseling",
            "phone_called": "9876543210",
            "duration_minutes": 15,
            "risk_indicators": {
                "child_marriage_risk": False,
                "school_dropout_risk": True,
                "health_concern": False,
            },
            "observations": "मुलीला पुढील शिक्षणासाठी मदत हवी आहे. पालकांशी चर्चा केली.",
            "notes": "पुढील आठवड्यात पुन्हा फोन करणे आणि कॉलेज प्रवेशाबाबत माहिती देणे.",
        },
    )
    assert res_call.status_code == 201, res_call.text
    call = res_call.json()
    assert call["external_girl_id"] == girl_id
    assert call["status"] == "completed"
    assert call["purpose"] == "counseling"
    assert call["duration_minutes"] == 15
    assert call["observations"] == "मुलीला पुढील शिक्षणासाठी मदत हवी आहे. पालकांशी चर्चा केली."
    call_id = call["id"]

    # 4. Check external girl profile has call summary updated
    res_get = client.get(f"{API}/external-girls/{girl_id}", headers=admin)
    assert res_get.status_code == 200
    girl_detail = res_get.json()
    assert girl_detail["call_summary"]["total_calls"] == 1
    assert girl_detail["call_summary"]["last_call_status"] == "completed"
    assert len(girl_detail["recent_calls"]) >= 1

    # Check eligible_for_call filter: girl called today should NOT appear for 1 month
    res_eligible = client.get(f"{API}/external-girls?eligible_for_call=true", headers=admin)
    assert res_eligible.status_code == 200
    assert not any(g["id"] == girl_id for g in res_eligible.json()["items"])

    # 5. List external calls
    res_calls = client.get(f"{API}/external-calls?external_girl_id={girl_id}", headers=admin)
    assert res_calls.status_code == 200
    assert any(c["id"] == call_id for c in res_calls.json()["items"])

    # 6. Update call
    res_up_call = client.patch(
        f"{API}/external-calls/{call_id}",
        headers=admin,
        json={"notes": "अपडेट: पालकांनी प्रवेशासाठी होकार दिला."},
    )
    assert res_up_call.status_code == 200
    assert "अपडेट: पालकांनी प्रवेशासाठी होकार दिला." in res_up_call.json()["notes"]

    # 7. Update girl profile
    res_up_girl = client.patch(
        f"{API}/external-girls/{girl_id}",
        headers=admin,
        json={"status": "follow_up", "standard": "12th"},
    )
    assert res_up_girl.status_code == 200
    assert res_up_girl.json()["status"] == "follow_up"

    # 8. Delete call
    res_del_call = client.delete(f"{API}/external-calls/{call_id}", headers=admin)
    assert res_del_call.status_code == 204

    # 9. Delete external girl
    res_del_girl = client.delete(f"{API}/external-girls/{girl_id}", headers=admin)
    assert res_del_girl.status_code == 204


def test_transfer_girl_to_external(client, admin, mongo):
    from bson import ObjectId

    # 1. Setup village and girl in mongo
    v_id = mongo.villages.insert_one({
        "name": "टेकाडी",
        "name_mr": "टेकाडी",
        "name_en": "Tekadi",
        "code": "09",
        "taluka_id": ObjectId(),
    }).inserted_id

    g_id = mongo.girls.insert_one({
        "name": "सीमा कांबळे",
        "name_en": "Seema Kamble",
        "girl_code": "KVP-09-01-050",
        "girl_seq": 50,
        "dob": None,
        "birth_year": 2008,
        "village_id": v_id,
        "phone": "9876500001",
        "household": {"father_name": "प्रकाश कांबळे", "phone": "9876500002", "address": "वॉर्ड २"},
        "school_status": "in_school",
        "school_name": "जि. प. शाळा",
        "standard": "10th",
        "enrollment": {"status": "active"},
        "is_deleted": False,
    }).inserted_id

    # 2. Transfer via POST /girls/{id}/transfer-to-external with removal reason
    res = client.post(
        f"{API}/girls/{g_id}/transfer-to-external",
        headers=admin,
        json={
            "reason": "लग्न झाल्यामुळे सासरी गेली",
            "notes": "फोनवरून समुपदेशन व मार्गदर्शन सुरू ठेवणे",
            "status": "active",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["external_girl"]["name"] == "सीमा कांबळे"
    assert data["external_girl"]["transferred_from_girl_code"] == "KVP-09-01-050"
    assert data["external_girl"]["transfer_reason"] == "लग्न झाल्यामुळे सासरी गेली"
    assert data["external_girl"]["transferred_from_village_name"] == "टेकाडी"
    assert data["external_girl"]["phone"] == "9876500001"
    assert data["external_girl"]["alt_phone"] == "9876500002"
    ext_id = data["external_girl_id"]

    # 3. Check original girl is removed from active village girls list
    res_girls = client.get(f"{API}/girls", headers=admin)
    assert not any(g["id"] == str(g_id) for g in res_girls.json()["items"])

    # Verify database document updated
    doc = mongo.girls.find_one({"_id": g_id})
    assert doc["is_deleted"] is True
    assert doc["enrollment"]["status"] == "transferred"
    assert "लग्न झाल्यामुळे" in doc["delete_reason"]

    # 4. Check external girl is visible in external girls list and searchable by girl_code
    res_ext = client.get(f"{API}/external-girls", headers=admin)
    assert res_ext.status_code == 200
    assert any(g["id"] == str(ext_id) for g in res_ext.json()["items"])

    res_search = client.get(f"{API}/external-girls?q=KVP-09-01-050", headers=admin)
    assert res_search.status_code == 200
    assert any(g["id"] == str(ext_id) for g in res_search.json()["items"])

    # 5. Confirm DELETE /girls/{id} is not supported (405 Method Not Allowed)
    res_del = client.delete(f"{API}/girls/{g_id}", headers=admin)
    assert res_del.status_code == 404


