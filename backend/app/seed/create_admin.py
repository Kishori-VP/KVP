"""Create or promote a Stakeholder (admin) or Super Admin account.

Usage:
  python -m app.seed.create_admin --name "Super Admin" --phone 9876543210 --email pc@example.org --role super_admin --password KvpDemo@123
"""

import argparse
import asyncio
import getpass
import re

from app.core.permissions import Role
from app.core.security import hash_password
from app.db import collections as c
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.services import audit
from app.utils.dates import utcnow


async def create(name: str, phone: str, email: str | None, password: str, role: str) -> None:
    await connect_to_mongo()
    db = get_database()
    await ensure_indexes(db)
    existing = await db[c.USERS].find_one({"$or": [{"phone": phone}] + ([{"email": email.lower()}] if email else [])})
    now = utcnow()
    if existing:
        await db[c.USERS].update_one(
            {"_id": existing["_id"]},
            {"$set": {"role": role, "name": name, "password_hash": hash_password(password), "is_active": True, "updated_at": now}}
        )
        print(f"User {existing['phone']} promoted/updated to {role}: {name}")
        await close_mongo_connection()
        return

    doc = {
        "name": name, "email": email.lower() if email else None, "phone": phone,
        "password_hash": hash_password(password), "role": role,
        "village_id": None, "village_ids": [], "taluka_id": None, "group_ids": [],
        "designation": "Stakeholder" if role in (Role.STAKEHOLDER.value, Role.SUPER_ADMIN.value) else "Admin",
        "contact": {}, "is_active": True, "created_by": None, "created_at": now, "updated_at": now, "last_login_at": None,
    }
    res = await db[c.USERS].insert_one(doc)
    await audit.log(db, None, "create", "user", res.inserted_id, f"Bootstrap {role} {name} created from CLI")
    print(f"{role.replace('_', ' ').title()} created: {name} ({phone})")
    await close_mongo_connection()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True)
    p.add_argument("--phone", required=True, help="10-digit mobile number (used to log in)")
    p.add_argument("--email")
    p.add_argument("--password")
    p.add_argument("--role", default="stakeholder", choices=["admin", "stakeholder", "super_admin"])
    args = p.parse_args()
    if not re.fullmatch(r"[6-9]\d{9}", args.phone):
        raise SystemExit("Phone must be a 10-digit Indian mobile number")
    password = args.password or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")
    asyncio.run(create(args.name, args.phone, args.email, password, args.role))


if __name__ == "__main__":
    main()
