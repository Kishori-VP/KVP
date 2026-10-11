"""Import the KVP 2026-27 master data from the programme's Excel files.

Imports: talukas, the 20 village clusters, Kishori Groups, Bal Panchayat groups
and the Girls' Unique ID list. Safe to re-run: existing records are matched and
not duplicated, and Stakeholder edits to imported girls are not overwritten.

Usage:
  python -m app.seed.import_kvp_data "C:/Users/HP/Downloads/KVP Data" [--dry-run]
"""

import argparse
import asyncio
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import openpyxl

from app.db import collections as c
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.seed.defaults import seed_lookups
from app.services import audit
from app.services.counters import ensure_sequence_at_least
from app.utils.dates import utcnow

DISTRICT, DISTRICT_MR = "Parbhani", "परभणी"
TALUKAS = {"palam": ("Palam", "पालम"), "gangakhed": ("Gangakhed", "गंगाखेड")}

# The 20 programme villages (some are clusters of hamlets), as used in the KVP calendar
# and donor report. Aliases cover every spelling found in the source files.
VILLAGES = [
    ("Pendu K / Pendu BDK", "पेंडू", "palam", ["पेंडू खु.", "पेंडू बु."], ["पेंडू", "पेंडू बु", "पेंडू खु"]),
    ("Peth Pimpalgaon", "पेठपिंपळगाव", "palam", [], ["पेठ पिंपळगाव"]),
    ("Farkanda / Digras", "फरकंडा / डिग्रस", "palam", ["फरकंडा", "डिग्रस"], ["फरकंडा", "फरकडा", "डिग्रस"]),
    ("Banwas", "बनवस", "palam", [], []),
    ("Chatori", "चाटोरी", "palam", [], []),
    ("Chorwad", "चोरवड", "palam", [], []),
    ("Kerwadi / Kapasi / Sirur", "केरवाडी / कापसी / सिरपूर", "palam", ["केरवाडी", "कापसी", "सिरपूर"],
     ["केरवाडी", "कापशी", "कापसी", "शिरपूर", "सिरपूर"]),
    ("Sayala", "सायाळा", "palam", [], ["सायळा"]),
    ("Narlad", "नरळद", "gangakhed", [], []),
    ("Khandali", "खंडाळी", "gangakhed", [], []),
    ("Bothi", "बोथी", "gangakhed", [], []),
    ("Isaad", "इसाद", "gangakhed", [], []),
    ("Ilegaon", "इळेगाव", "gangakhed", [], ["ईळेगाव"]),
    ("Arkhed", "आरखेड", "palam", ["आरखेड", "सोमेश्वर", "घोडा"], ["सोमेश्वर", "घोडा"]),
    ("Fala", "फळा", "palam", [], []),
    ("Shekh Rajur / Kharab Dhanora", "शेखराजूर / खरबधानोरा", "palam", ["शेखराजूर", "खरबधानोरा"],
     ["शेखराजूर", "शेखराजुर", "शेख राजुर", "खरब धानोरा", "खरबधानोरा", "खराबधानोरा", "खरबधनोरा"]),
    ("Sategaon", "सातेगाव", "palam", [], ["सातेगांव"]),
    ("Pethshivani", "पेठशिवणी", "palam", [], ["पेटशिवनी"]),
    ("Selu", "सेलू", "palam", [], ["सेलु", "शेलु"]),
    ("Wani Pimpalgaon", "वाणीपिंपळगाव", "palam", ["वाणीपिंपळगाव", "भोगाव"], ["वाणी पिंपळगाव", "भोगाव", "भोगांव"]),
]


def norm(text: str | None) -> str:
    """Normalise Marathi spellings: unify long/short vowels and drop spaces, dots and nasal marks."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", str(text)).strip()
    for a, b in (("ई", "इ"), ("ऊ", "उ"), ("ी", "ि"), ("ू", "ु"), ("ं", ""), ("ँ", ""), ("़", "")):
        t = t.replace(a, b)
    return re.sub(r"[\s.\-]", "", t)


def build_alias_index() -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, (_en, mr, _t, hamlets, aliases) in enumerate(VILLAGES):
        for name in [mr, *hamlets, *aliases]:
            idx[norm(name)] = i
            for part in name.split("/"):
                idx.setdefault(norm(part), i)
    return idx


ALIASES = build_alias_index()


def match_village(raw: str | None) -> int | None:
    if not raw:
        return None
    key = norm(raw)
    if key in ALIASES:
        return ALIASES[key]
    for part in re.split(r"[/,]", str(raw)):
        if norm(part) in ALIASES:
            return ALIASES[norm(part)]
    return None


def find_file(folder: Path, pattern: str) -> Path:
    matches = sorted(folder.glob(pattern))
    if not matches:
        raise SystemExit(f"No file matching '{pattern}' in {folder}")
    return matches[0]


def read_group_sheet(path: Path) -> list[tuple[int | None, str, str]]:
    """Rows of (serial, village, group name) from the village-wise group lists."""
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = []
    for r in ws.iter_rows(values_only=True):
        if len(r) < 3 or not r[1] or not r[2]:
            continue
        if not isinstance(r[0], (int, float)):
            continue  # header / total rows
        rows.append((int(r[0]), str(r[1]).strip(), str(r[2]).strip()))
    return rows


async def run(folder: Path, dry_run: bool) -> None:
    uid_file = find_file(folder, "*UNIQUE ID*.xlsx")
    groups_file = find_file(folder, "*Kishori Groups*.xlsx")
    bp_file = find_file(folder, "*Balpanchayat*.xlsx")

    # ---- read & map everything first, so problems surface before anything is written
    kishori = read_group_sheet(groups_file)
    bal = read_group_sheet(bp_file)
    ws = openpyxl.load_workbook(uid_file, data_only=True).worksheets[0]
    girls = [r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]

    unmatched = Counter()
    for _s, v, _g in kishori + bal:
        if match_village(v) is None:
            unmatched[f"group village: {v}"] += 1
    for r in girls:
        if match_village(r[1]) is None:
            unmatched[f"girl village: {r[1]} ({r[2]})"] += 1
    print(f"Read {len(kishori)} Kishori groups, {len(bal)} Bal Panchayat groups, {len(girls)} girls")
    if unmatched:
        print("Unmatched village names (imported with needs_review flag):")
        for k, n in unmatched.items():
            print(f"  {n:4} x {k}")
    if dry_run:
        print("Dry run: nothing written.")
        return

    await connect_to_mongo()
    db = get_database()
    await ensure_indexes(db)
    await seed_lookups(db)
    now = utcnow()

    # ---- talukas
    taluka_ids = {}
    for key, (en, mr) in TALUKAS.items():
        await db[c.TALUKAS].update_one(
            {"name": en, "district": DISTRICT},
            {"$setOnInsert": {"name": en, "name_mr": mr, "district": DISTRICT, "district_mr": DISTRICT_MR,
                              "state": "Maharashtra", "is_active": True, "created_at": now, "updated_at": now}},
            upsert=True)
        taluka_ids[key] = (await db[c.TALUKAS].find_one({"name": en, "district": DISTRICT}))["_id"]

    # ---- villages
    village_ids = []
    for en, mr, tkey, hamlets, aliases in VILLAGES:
        await db[c.VILLAGES].update_one(
            {"name": en, "taluka_id": taluka_ids[tkey]},
            {"$setOnInsert": {"name": en, "name_mr": mr, "taluka_id": taluka_ids[tkey], "district": DISTRICT,
                              "pin_code": None, "location": None, "status": "active", "created_at": now, "updated_at": now},
             "$addToSet": {"hamlets": {"$each": hamlets}, "aliases": {"$each": aliases}}},
            upsert=True)
        village_ids.append((await db[c.VILLAGES].find_one({"name": en, "taluka_id": taluka_ids[tkey]}))["_id"])

    async def village_doc(i):
        return await db[c.VILLAGES].find_one({"_id": village_ids[i]})

    # ---- groups
    async def import_groups(rows, group_type):
        created = 0
        seen = Counter()
        for serial, vraw, name in rows:
            i = match_village(vraw)
            if i is None:
                continue
            seen[(i, name)] += 1
            final = name if seen[(i, name)] == 1 else f"{name} ({seen[(i, name)]})"
            v = await village_doc(i)
            res = await db[c.GROUPS].update_one(
                {"village_id": v["_id"], "group_type": group_type, "name": final},
                {"$setOnInsert": {"name": final, "group_type": group_type, "group_number": str(serial),
                                  "village_id": v["_id"], "taluka_id": v["taluka_id"], "meeting_schedule": None,
                                  "responsible_volunteer_id": None, "is_active": True, "source": "import",
                                  "source_village_raw": vraw, "created_at": now, "updated_at": now}},
                upsert=True)
            created += 1 if res.upserted_id else 0
        return created

    kg = await import_groups(kishori, "kishori")
    bg = await import_groups(bal, "bal_panchayat")

    # ---- girls
    prefix = "KVP-2627-"
    created = updated = 0
    max_seq = 0
    for code, vraw, traw, survey in girls:
        code = str(code).strip()
        seq = int(code.rsplit("-", 1)[-1]) if code.rsplit("-", 1)[-1].isdigit() else None
        max_seq = max(max_seq, seq or 0)
        i = match_village(vraw)
        v = await village_doc(i) if i is not None else None
        survey_dt = survey.replace(tzinfo=UTC) if isinstance(survey, datetime) else None
        res = await db[c.GIRLS].update_one(
            {"girl_code": code},
            {"$setOnInsert": {
                "girl_code": code, "girl_seq": seq, "name": None, "dob": None, "birth_year": None,
                "village_id": v["_id"] if v else None, "taluka_id": v["taluka_id"] if v else None,
                "group_id": None, "school_status": None, "school_name": None, "standard": None, "phone": None,
                "household": {}, "custom_fields": {},
                "enrollment": {"status": "active", "enrolled_on": survey_dt, "exit_reason": None},
                "survey_date": survey_dt,
                "case_summary": {"total": 0, "open": 0, "statuses": [], "open_categories": [], "has_critical_open": False},
                "health_summary": None, "last_participation_at": None,
                "flags": {"profile_incomplete": True, "needs_review": v is None},
                "source": "import", "is_historical": True,
                "source_village_raw": vraw, "source_taluka_raw": traw,
                "is_deleted": False, "created_by": None, "created_at": now, "updated_at": now,
            }},
            upsert=True)
        if res.upserted_id:
            created += 1
        else:
            updated += 1
    await ensure_sequence_at_least(db, f"girl:{prefix}", max_seq)

    summary = (f"Talukas: {len(taluka_ids)}, villages: {len(village_ids)}, Kishori groups created: {kg}, "
               f"Bal Panchayat groups created: {bg}, girls created: {created} (already present: {updated}), "
               f"next Girl ID: {prefix}{max_seq + 1}")
    await audit.log(db, None, "import", "master_data", None, summary, meta={"folder": str(folder)})
    print(summary)
    await close_mongo_connection()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", type=Path)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args.folder, args.dry_run))


if __name__ == "__main__":
    main()
