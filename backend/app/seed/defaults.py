"""Default lookup values, taken from the KVP 2026-27 calendar and daily-report form.

Seeding uses $setOnInsert, so Stakeholder edits are never overwritten.
Run: python -m app.seed.defaults
"""

import asyncio

from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.utils.dates import utcnow

# (code, label, label_mr, attributes)
DEFAULT_LOOKUPS: dict[str, list[tuple[str, str, str | None, dict]]] = {
    "event_type": [
        ("kishori_meeting", "Kishori group meeting", "किशोरी मिटिंग", {"is_meeting": True}),
        ("bal_panchayat_meeting", "Bal Panchayat meeting", "बालपंचायत मिटिंग", {"is_meeting": True}),
        ("health_camp", "Health camp", "हेल्थ कॅम्प", {"health": True}),
        ("hb_checkup", "Haemoglobin (Hb) check-up", "HB चेकअप", {"health": True}),
        ("mental_wellbeing", "Mental wellbeing session", "मनाचे आरोग्य", {}),
        ("stakeholder_meeting", "Stakeholder meeting", "स्टेक होल्डर मिटिंग", {}),
        ("special_training", "Special training", "विशेष ट्रेनिंग", {}),
        ("leadership_training", "Leader girls' training", "लीडर मुलींचे ट्रेनिंग", {}),
        ("science_centre_visit", "Science centre visit", "सायन्स सेंटर व्हिजीट", {}),
        ("gender_equality", "Gender equality session", "स्त्री पुरुष समानता", {}),
        ("talent_competition", "Talent competition", "विविध गुणदर्शन स्पर्धा", {}),
        ("cyber_security_awareness", "Cyber security awareness", "सायबर सिक्युरिटी अवेरनेस", {}),
        ("self_defence", "Self-defence training", "सेल्फ डिफेन्स", {}),
        ("excursion", "Excursion / study tour", "सहल", {}),
        ("library_follow_up", "Library follow-up", "वाचनालय पाठपुरावा", {}),
        ("awareness_session", "Awareness session", "जनजागृती सत्र", {}),
        ("other", "Other", "इतर", {}),
    ],
    "activity_type": [
        ("kishori_group_meeting", "Kishori group meeting", "किशोरी गट सभा", {}),
        ("home_visit", "Home / parent visit", "गृह भेटी / पालक भेटी", {}),
        ("mental_wellbeing_training", "Mental wellbeing training", "मनाचे आरोग्य ट्रेनिंग", {}),
        ("health_camp", "Health camp", "हेल्थ कॅम्प", {}),
        ("bal_panchayat", "Bal Panchayat", "बाल पंचायत", {}),
        ("leadership_activity", "Leadership activity", "नेतृत्व उपक्रम", {}),
        ("awareness_session", "Awareness session", "जनजागृती सत्र", {}),
        ("stakeholder_meeting", "Stakeholder meeting", "स्टेक होल्डर मिटिंग", {}),
        ("other_work", "Other work", "इतर काम", {}),
    ],
    "case_category": [
        ("child_marriage_risk", "Child marriage risk", "बालविवाह धोका", {}),
        ("school_dropout", "School dropout", "शाळा गळती", {}),
        ("health_anaemia", "Health / anaemia", "आरोग्य / रक्तक्षय", {}),
        ("gender_discrimination", "Gender discrimination", "लिंगभेद", {}),
        ("mental_health", "Mental health concern", "मानसिक आरोग्य", {}),
        ("protection", "Violence / protection concern", "हिंसा / संरक्षण", {}),
        ("other", "Other", "इतर", {}),
    ],
    "target_type": [
        ("home_visits", "House visits", "गृह भेटी", {"metric": "home_visits"}),
        ("group_meetings", "Group meetings", "गट सभा", {"metric": "group_meetings"}),
        ("events", "Events conducted", "कार्यक्रम", {"metric": "events"}),
        ("girls_covered", "Girls covered", "मुलींपर्यंत पोहोच", {"metric": "girls_covered"}),
        ("follow_ups", "Follow-ups", "पाठपुरावा", {"metric": "follow_ups"}),
        ("case_closures", "Case closures", "प्रकरणे निकाली", {"metric": "case_closures"}),
        ("health_screenings", "Health screenings", "आरोग्य तपासणी", {"metric": "health_screenings"}),
        ("daily_reports", "Daily reports submitted", "दैनिक अहवाल", {"metric": "activity_reports"}),
    ],
    "contact_category": [
        ("hospital_head", "Government hospital/clinic head or main doctor", "शासकीय रुग्णालय / दवाखाना प्रमुख", {"mandatory": True}),
        ("police_patil", "Police Patil", "पोलीस पाटील", {"mandatory": True}),
        ("sarpanch", "Sarpanch", "सरपंच", {"mandatory": True}),
        ("talathi", "Talathi", "तलाठी", {"mandatory": True}),
        ("asha_worker", "ASHA worker", "आशा ताई", {}),
        ("anganwadi_worker", "Anganwadi worker", "अंगणवाडी ताई", {}),
        ("crp", "CRP (Community Resource Person)", "CRP ताई", {}),
        ("school_contact", "School contact", "शाळा संपर्क", {}),
        ("gram_panchayat_member", "Gram Panchayat member", "ग्रामपंचायत सदस्य", {}),
        ("emergency_contact", "Emergency contact", "आपत्कालीन संपर्क", {}),
        ("other", "Other approved role", "इतर मान्यवर", {}),
    ],
    "school_status": [
        ("studying", "Studying", "शिकत आहे", {}),
        ("dropped_out", "Dropped out", "शाळा सोडली", {}),
        ("never_enrolled", "Never enrolled", "शाळेत दाखल नाही", {}),
        ("completed", "Completed schooling", "शिक्षण पूर्ण", {}),
        ("unknown", "Unknown", "माहिती नाही", {}),
    ],
    "health_field": [
        ("ifa_tablets", "Taking IFA tablets", "लोहयुक्त गोळ्या घेते", {"data_type": "boolean"}),
        ("deworming", "Deworming done", "जंतनाशक गोळी घेतली", {"data_type": "boolean"}),
        ("menstrual_hygiene_aware", "Aware of menstrual hygiene", "मासिक पाळी स्वच्छता माहिती", {"data_type": "boolean"}),
        ("uses_sanitary_pads", "Uses sanitary pads", "सॅनिटरी पॅड वापरते", {"data_type": "boolean"}),
        ("hb_test_method", "Hb test method", "Hb तपासणी पद्धत", {"data_type": "select", "options": ["digital", "sahli", "lab", "other"]}),
        ("referred_to_phc", "Referred to PHC", "PHC ला संदर्भित", {"data_type": "boolean"}),
    ],
}


async def seed_lookups(db: AsyncDatabase) -> int:
    created = 0
    now = utcnow()
    for type_, items in DEFAULT_LOOKUPS.items():
        for order, (code, label, label_mr, attrs) in enumerate(items):
            res = await db[c.LOOKUPS].update_one(
                {"type": type_, "code": code},
                {"$setOnInsert": {"type": type_, "code": code, "label": label, "label_mr": label_mr, "attributes": attrs,
                                  "order": order, "is_active": True, "is_system": True, "description": None,
                                  "created_at": now, "updated_at": now}},
                upsert=True,
            )
            created += 1 if res.upserted_id else 0
    return created


async def main() -> None:
    await connect_to_mongo()
    db = get_database()
    await ensure_indexes(db)
    print(f"Lookups created: {await seed_lookups(db)}")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
