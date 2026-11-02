"""Verify and correct Balpanchayat members: clean names, assign gender, and correct inconsistencies."""

import asyncio
from bson import ObjectId
from app.db.mongodb import connect_to_mongo, get_database, close_mongo_connection
from app.db import collections as c
from app.utils.gender import clean_child_name, infer_gender
from app.utils.translit import to_latin
from app.utils.dates import utcnow

async def run_fix():
    await connect_to_mongo()
    db = get_database()
    
    bp_groups = await db[c.GROUPS].find({"group_type": "bal_panchayat"}).to_list()
    print(f"Found {len(bp_groups)} Balpanchayat groups.")
    
    total_members = 0
    total_girls = 0
    total_boys = 0
    name_corrections = 0
    girl_id_corrections = 0
    now = utcnow()
    
    for group in bp_groups:
        members = group.get("members", [])
        if not members:
            continue
            
        updated_members = []
        group_modified = False
        
        for idx, m in enumerate(members):
            total_members += 1
            orig_name = m.get("name", "").strip()
            cleaned_name = clean_child_name(orig_name)
            
            if orig_name != cleaned_name:
                name_corrections += 1
                group_modified = True
                print(f"[{group['name']}] Corrected name: '{orig_name}' -> '{cleaned_name}'")
                
            gender = infer_gender(cleaned_name)
            if gender == "girl":
                total_girls += 1
            else:
                total_boys += 1
                
            # If gender was not set or changed
            if m.get("gender") != gender:
                group_modified = True
                
            girl_id = m.get("girl_id")
            if gender == "boy" and girl_id:
                girl_id_corrections += 1
                group_modified = True
                print(f"[{group['name']}] Removed invalid girl_id link ({girl_id}) from boy member '{cleaned_name}'")
                # Also check if that girl has this group as bal_panchayat_id and clear it
                try:
                    girl_oid = ObjectId(girl_id) if isinstance(girl_id, str) else girl_id
                    await db[c.GIRLS].update_one(
                        {"_id": girl_oid, "bal_panchayat_id": group["_id"]},
                        {"$set": {"bal_panchayat_id": None, "updated_at": now}}
                    )
                except Exception as e:
                    print(f"Error updating girl {girl_id}: {e}")
                girl_id = None
                
            # Ensure _id and id are present
            cid = m.get("_id") or ObjectId()
            if isinstance(cid, str):
                try:
                    cid = ObjectId(cid)
                except Exception:
                    cid = ObjectId()
            
            member_doc = {
                **m,
                "_id": cid,
                "id": str(cid),
                "name": cleaned_name,
                "name_en": to_latin(cleaned_name),
                "gender": gender,
                "girl_id": girl_id,
                "standard": m.get("standard"),
                "phone": m.get("phone"),
                "age": m.get("age"),
                "updated_at": now
            }
            updated_members.append(member_doc)
            
        if group_modified or True: # Save updated members with assigned gender and ids
            await db[c.GROUPS].update_one(
                {"_id": group["_id"]},
                {"$set": {"members": updated_members, "updated_at": now}}
            )
            
    print(f"\nBalpanchayat members update completed:")
    print(f"  Total members processed: {total_members}")
    print(f"  Girls assigned: {total_girls}")
    print(f"  Boys assigned: {total_boys}")
    print(f"  Name corrections made: {name_corrections}")
    print(f"  Boy girl_id corrections made: {girl_id_corrections}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(run_fix())
