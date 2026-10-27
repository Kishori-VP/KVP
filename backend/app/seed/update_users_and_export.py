"""
Update user credentials in MongoDB Atlas and export to Excel sheet.
"""

import asyncio
from datetime import datetime, timezone
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.core.security import hash_password
from app.db import collections as c
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database

USER_DATA = [
    {
        "name": "Dhondiram Sarang",
        "login_id": "9922914102",
        "phone": "9922914102",
        "email": None,
        "password": "Dhondiram@14102",
        "role": "super_admin",
        "display_role": "Super Admin",
        "designation": "Super Admin",
    },
    {
        "name": "Aradhana Kulkarni",
        "login_id": "8793504938",
        "phone": "8793504938",
        "email": None,
        "password": "Aradhana@04938",
        "role": "super_admin",
        "display_role": "Super Admin",
        "designation": "Super Admin",
    },
    {
        "name": "Development",
        "login_id": "syncaidevelopment@gmail.com",
        "phone": None,
        "email": "syncaidevelopment@gmail.com",
        "password": "Development@2026",
        "role": "super_admin",
        "display_role": "Super Admin",
        "designation": "Technical Super Admin",
    },
    {
        "name": "Gawlan Shinde",
        "login_id": "7350833881",
        "phone": "7350833881",
        "email": None,
        "password": "Gawlan@33881",
        "role": "admin_1",
        "display_role": "Admin-1",
        "designation": "Admin-1",
    },
    {
        "name": "Meera Poul",
        "login_id": "8788743959",
        "phone": "8788743959",
        "email": None,
        "password": "Meera@43959",
        "role": "admin_1",
        "display_role": "Admin-1",
        "designation": "Admin-1",
    },
    {
        "name": "Manmat Gadamwad",
        "login_id": "9922914127",
        "phone": "9922914127",
        "email": None,
        "password": "Manmat@14127",
        "role": "admin_2",
        "display_role": "Admin-2",
        "designation": "Admin-2",
    },
    {
        "name": "Ganga Mane",
        "login_id": "9922914123",
        "phone": "9922914123",
        "email": None,
        "password": "Ganga@14123",
        "role": "admin_2",
        "display_role": "Admin-2",
        "designation": "Admin-2",
    },
    {
        "name": "Manisha Shinde",
        "login_id": "7249877698",
        "phone": "7249877698",
        "email": None,
        "password": "Manisha@77698",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
    {
        "name": "Pooja Poul",
        "login_id": "9226448013",
        "phone": "9226448013",
        "email": None,
        "password": "Pooja@48013",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
    {
        "name": "Jyoti Mule",
        "login_id": "8766518846",
        "phone": "8766518846",
        "email": None,
        "password": "Jyoti@18846",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
    {
        "name": "Sulochana Bhusnar",
        "login_id": "7767973312",
        "phone": "7767973312",
        "email": None,
        "password": "Sulochana@73312",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
    {
        "name": "Vijaymala Gurav",
        "login_id": "8208574422",
        "phone": "8208574422",
        "email": None,
        "password": "Vijaymala@74422",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
    {
        "name": "Mangal Shete",
        "login_id": "7776815249",
        "phone": "7776815249",
        "email": None,
        "password": "Mangal@15249",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
    {
        "name": "Shobha Kulkarni",
        "login_id": "9730119757",
        "phone": "9730119757",
        "email": None,
        "password": "Shobha@19757",
        "role": "volunteer",
        "display_role": "User (Volunteer)",
        "designation": "Tai (Volunteer)",
    },
]


async def update_database():
    await connect_to_mongo()
    db = get_database()
    now = datetime.now(timezone.utc)

    # Migrate any remaining stakeholder or generic admin accounts
    res_stk = await db[c.USERS].update_many({"role": "stakeholder"}, {"$set": {"role": "super_admin", "updated_at": now}})
    if res_stk.modified_count:
        print(f"Migrated {res_stk.modified_count} stakeholder account(s) to super_admin")

    for item in USER_DATA:
        hashed = hash_password(item["password"])
        query = {}
        if item["email"]:
            query["$or"] = [{"email": item["email"].lower()}, {"name": item["name"]}]
        else:
            query["$or"] = [{"name": item["name"]}]
            if item["phone"]:
                query["$or"].append({"phone": item["phone"]})

        existing = await db[c.USERS].find_one(query)
        if existing:
            update_fields = {
                "name": item["name"],
                "role": item["role"],
                "password_hash": hashed,
                "is_active": True,
                "updated_at": now,
            }
            if item["phone"]:
                update_fields["phone"] = item["phone"]
            if item["email"]:
                update_fields["email"] = item["email"].lower()
            if not existing.get("designation"):
                update_fields["designation"] = item["designation"]

            await db[c.USERS].update_one({"_id": existing["_id"]}, {"$set": update_fields})
            print(f"Updated user: {item['name']} (ID: {existing['_id']}, Role: {item['role']})")
        else:
            doc = {
                "name": item["name"],
                "email": item["email"].lower() if item["email"] else None,
                "phone": item["phone"],
                "password_hash": hashed,
                "role": item["role"],
                "village_id": None,
                "village_ids": [],
                "taluka_id": None,
                "group_ids": [],
                "designation": item["designation"],
                "contact": {},
                "is_active": True,
                "created_by": None,
                "created_at": now,
                "updated_at": now,
                "last_login_at": None,
            }
            res = await db[c.USERS].insert_one(doc)
            print(f"Created user: {item['name']} (ID: {res.inserted_id}, Role: {item['role']})")

    await close_mongo_connection()


def export_excel(output_path: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "KVP User Credentials"

    # Header styling
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=11)
    bold_font = Font(name="Calibri", size=11, bold=True)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # Title Banner
    ws.merge_cells("A1:E1")
    title_cell = ws["A1"]
    title_cell.value = "Kishori Vikas Program (KVP) - User Credentials & Access Directory"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="1F4E79")
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:E2")
    sub_cell = ws["A2"]
    sub_cell.value = f"Generated on: {datetime.now().strftime('%d %B %Y')} | Confidential"
    sub_cell.font = Font(name="Calibri", size=10, italic=True, color="595959")
    sub_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 18

    # Table Headers
    headers = ["Sr No.", "Full Name", "Role", "Login ID (Mobile / Email)", "Password"]
    ws.row_dimensions[4].height = 24

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    # Table Rows
    alt_fill = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")

    for row_idx, item in enumerate(USER_DATA, start=5):
        ws.row_dimensions[row_idx].height = 20
        fill = alt_fill if row_idx % 2 == 1 else None

        c_sr = ws.cell(row=row_idx, column=1, value=row_idx - 4)
        c_sr.alignment = center_align

        c_name = ws.cell(row=row_idx, column=2, value=item["name"])
        c_name.alignment = left_align
        c_name.font = bold_font

        c_role = ws.cell(row=row_idx, column=3, value=item["display_role"])
        c_role.alignment = center_align

        c_login = ws.cell(row=row_idx, column=4, value=item["login_id"])
        c_login.alignment = center_align
        c_login.number_format = "@"

        c_pass = ws.cell(row=row_idx, column=5, value=item["password"])
        c_pass.alignment = center_align
        c_pass.font = bold_font

        for cell in (c_sr, c_name, c_role, c_login, c_pass):
            if fill:
                cell.fill = fill
            cell.border = thin_border
            if cell != c_name and cell != c_pass:
                cell.font = data_font

    # Column Widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row < 4:
                continue
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 5, 12)

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 25
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 32
    ws.column_dimensions["E"].width = 22

    wb.save(output_path)
    print(f"Excel file successfully generated at: {output_path}")


if __name__ == "__main__":
    asyncio.run(update_database())
    export_excel("d:\\syncAi\\sedt\\KVP\\KVP_User_Credentials.xlsx")
