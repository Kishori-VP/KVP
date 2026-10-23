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
