"""Create the first Stakeholder (admin) account.

Usage:
  python -m app.seed.create_admin --name "Programme Coordinator" --phone 9876543210 --email pc@example.org
  (prompts for the password; or pass --password for non-interactive setups)
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


async def create(name: str, phone: str, email: str | None, password: str) -> None:
    await connect_to_mongo()
    db = get_database()
    await ensure_indexes(db)
    if await db[c.USERS].find_one({"$or": [{"phone": phone}] + ([{"email": email.lower()}] if email else [])}):
        print("A user with this phone or email already exists.")
        await close_mongo_connection()
        return
    now = utcnow()
    doc = {
        "name": name, "email": email.lower() if email else None, "phone": phone,
        "password_hash": hash_password(password), "role": Role.STAKEHOLDER.value,
        "village_id": None, "taluka_id": None, "group_ids": [], "designation": "Programme Coordinator",
        "contact": {}, "is_active": True, "created_by": None, "created_at": now, "updated_at": now, "last_login_at": None,
    }
    res = await db[c.USERS].insert_one(doc)
    await audit.log(db, None, "create", "user", res.inserted_id, f"Bootstrap Stakeholder {name} created from CLI")
    print(f"Stakeholder created: {name} ({phone})")
    await close_mongo_connection()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True)
    p.add_argument("--phone", required=True, help="10-digit mobile number (used to log in)")
    p.add_argument("--email")
    p.add_argument("--password")
    args = p.parse_args()
    if not re.fullmatch(r"[6-9]\d{9}", args.phone):
        raise SystemExit("Phone must be a 10-digit Indian mobile number")
    password = args.password or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")
    asyncio.run(create(args.name, args.phone, args.email, password))


if __name__ == "__main__":
    main()
