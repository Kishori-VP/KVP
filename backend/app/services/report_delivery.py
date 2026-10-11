"""Generate, store and share report files (on demand or on a schedule)."""

import asyncio
import smtplib
from datetime import UTC, date, datetime, time, timedelta
from email.message import EmailMessage

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.db import collections as c
from app.services import exporters, notifications
from app.services.app_settings import get_setting
from app.services.reports import apply_template, build_report
from app.utils.dates import local_tz, period_bounds, previous_period, today_local, utcnow

FREQUENCY_PERIOD = {"daily": "daily", "weekly": "weekly", "monthly": "monthly", "quarterly": "quarterly", "yearly": "yearly"}


def next_run_after(frequency: str, after: date, run_time: str = "07:00") -> datetime:
    """Next run moment (UTC) strictly after the given local date."""
    h, m = map(int, run_time.split(":"))
    if frequency == "daily":
        d = after + timedelta(days=1)
    elif frequency == "weekly":
        d = after + timedelta(days=7 - after.weekday())  # next Monday
    else:
        d = period_bounds(FREQUENCY_PERIOD[frequency], after)[1] + timedelta(days=1)
    return datetime.combine(d, time(h, m), tzinfo=local_tz()).astimezone(UTC)


async def validate_recipients(db: AsyncDatabase, user_ids: list[ObjectId], emails: list[str]) -> list[dict]:
    users = await db[c.USERS].find({"_id": {"$in": user_ids}, "is_active": True}, {"name": 1, "email": 1}).to_list()
    if len(users) != len(set(user_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Recipients must be active users")
    allowed = {e.lower() for e in (await get_setting(db, "report_sharing"))["allowed_external_emails"]}
    known = {u["email"] for u in await db[c.USERS].find({"email": {"$in": [e.lower() for e in emails]}, "is_active": True}).to_list()}
    bad = [e for e in emails if e.lower() not in allowed and e.lower() not in known]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Not authorised recipients: {bad}. Add them under /config/settings/report_sharing.")
    return users


def _send_email(to: list[str], subject: str, body: str, files: list[tuple[str, bytes, str]]) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    for name, data, mime in files:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


async def generate_and_share(
    db: AsyncDatabase,
    *,
    report_type: str,
    period: str,
    reference: date | None,
    start: date | None,
    end: date | None,
    formats: list[str],
    taluka_id=None,
    village_id=None,
    recipient_user_ids: list[ObjectId] | None = None,
    recipient_emails: list[str] | None = None,
    actor: dict | None = None,
    schedule_id: ObjectId | None = None,
    template: dict | None = None,
) -> dict:
    users = await validate_recipients(db, recipient_user_ids or [], recipient_emails or [])
    report = await build_report(db, report_type, period, reference, start, end, taluka_id, village_id)
    if template:
        report = apply_template(report, template)
    now = utcnow()
    folder = settings.reports_dir / f"{now:%Y/%m}"
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{report_type}_{report['period']['start']:%Y%m%d}-{report['period']['end']:%Y%m%d}_{now:%H%M%S}"
    files, attachments = [], []
    for fmt in formats:
        data, mime, ext = exporters.render(report, fmt)
        path = folder / f"{stem}.{ext}"
        path.write_bytes(data)
        files.append({"format": ext, "path": path.relative_to(settings.reports_dir).as_posix(), "size_bytes": len(data),
                      "content_type": mime})
        attachments.append((path.name, data, mime))

    doc = {
        "report_type": report_type,
        "title": report["title"],
        "subtitle": report["subtitle"],
        "period": {"type": period, "start": datetime.combine(report["period"]["start"], time.min, tzinfo=UTC),
                   "end": datetime.combine(report["period"]["end"], time.min, tzinfo=UTC), "label": report["period"]["label"]},
        "files": files,
        "schedule_id": schedule_id,
        "template_id": template["_id"] if template else None,
        "generated_by": actor["_id"] if actor else None,
        "recipient_user_ids": [u["_id"] for u in users],
        "recipient_emails": recipient_emails or [],
        "delivery": {"in_app": 0, "email": "not_requested"},
        "created_at": now,
    }
    res = await db[c.GENERATED_REPORTS].insert_one(doc)
    doc["_id"] = res.inserted_id

    for u in users:
        if await notifications.notify(db, u["_id"], "report_ready", f"Report ready: {report['title']}",
                                      report["period"]["label"], entity_type="generated_report", entity_id=res.inserted_id):
            doc["delivery"]["in_app"] += 1
    emails = sorted({*(recipient_emails or []), *[u["email"] for u in users if u.get("email")]})
    if emails:
        if settings.smtp_configured:
            try:
                await asyncio.to_thread(_send_email, emails, f"{settings.app_name}: {report['title']}",
                                        f"{report['title']}\n{report['subtitle']}\n{report['period']['label']}\n\n"
                                        "The report is attached.", attachments)
                doc["delivery"]["email"] = f"sent to {len(emails)}"
            except (OSError, smtplib.SMTPException) as exc:
                doc["delivery"]["email"] = f"failed: {exc}"
        else:
            doc["delivery"]["email"] = "skipped: SMTP not configured"
    await db[c.GENERATED_REPORTS].update_one({"_id": res.inserted_id}, {"$set": {"delivery": doc["delivery"]}})
    return doc


async def run_due_schedules(db: AsyncDatabase) -> int:
    """Run every active schedule whose next_run_at has passed. Returns how many ran."""
    ran = 0
    now = utcnow()
    async for sch in db[c.REPORT_SCHEDULES].find({"is_active": True, "next_run_at": {"$lte": now}}):
        today = today_local()
        period = FREQUENCY_PERIOD[sch["frequency"]]
        # Report on the period that has just finished.
        start, end = previous_period(period, period_bounds(period, today)[0])
        result = {"status": "ok", "error": None}
        try:
            out = await run_schedule(db, sch, start, end)
            result["generated_report_id"] = out["_id"]
        except Exception as exc:  # keep the scheduler alive; the error is recorded on the schedule
            result = {"status": "error", "error": str(exc)[:500]}
        await db[c.REPORT_SCHEDULES].update_one({"_id": sch["_id"]}, {"$set": {
            "last_run_at": now, "last_result": result,
            "next_run_at": next_run_after(sch["frequency"], today, sch.get("run_time", "07:00"))}})
        ran += 1
    return ran


async def schedule_template(db: AsyncDatabase, sch: dict) -> dict | None:
    if not sch.get("template_id"):
        return None
    tpl = await db[c.REPORT_TEMPLATES].find_one({"_id": sch["template_id"], "is_active": True})
    if not tpl:
        raise ValueError("The schedule's report template was deleted or deactivated")
    return tpl


async def run_schedule(db: AsyncDatabase, sch: dict, start: date, end: date, actor: dict | None = None) -> dict:
    tpl = await schedule_template(db, sch)
    return await generate_and_share(
        db, report_type=tpl["report_type"] if tpl else sch["report_type"], period="custom", reference=None,
        start=start, end=end, formats=sch["formats"],
        # Schedule scope wins; otherwise fall back to the template's scope.
        taluka_id=sch.get("taluka_id") or (tpl or {}).get("taluka_id"),
        village_id=sch.get("village_id") or (tpl or {}).get("village_id"),
        recipient_user_ids=sch.get("recipient_user_ids", []), recipient_emails=sch.get("recipient_emails", []),
        actor=actor, schedule_id=sch["_id"], template=tpl)
