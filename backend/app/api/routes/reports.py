"""Reports & analytics (PRD 4.14): on-demand reports, exports, schedules and sharing."""

from datetime import date
from typing import Literal, get_args

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.deps import Db, Pagination, Stakeholder
from app.db import collections as c
from app.services import audit, exporters
from app.services.exporters import FORMAT_LABELS, ExportFormat
from app.services.report_delivery import (
    FREQUENCY_PERIOD,
    generate_and_share,
    next_run_after,
    run_schedule,
    validate_recipients,
)
from app.services.reports import REPORT_TYPES, build_report
from app.utils.dates import PeriodType, period_bounds, previous_period, today_local, utcnow
from app.utils.mongo import ObjectIdStr, get_or_404, oid, oids, paginate, serialize

router = APIRouter(prefix="/reports", tags=["reports"])


def parse_formats(formats: str | None, single: str) -> list[str] | None:
    """`formats=pdf,csv` (comma-separated) wins over the single `format`; None means return JSON."""
    if not formats:
        return None if single == "json" else [single]
    chosen = [f.strip().lower() for f in formats.split(",") if f.strip()]
    unknown = [f for f in chosen if f not in get_args(ExportFormat)]
    if unknown or not chosen:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Unknown format(s) {unknown}. Use any of {list(get_args(ExportFormat))}")
    return list(dict.fromkeys(chosen))


def export_response(report: dict, formats: list[str], stem: str,
                    extra: list[tuple[str, bytes, str]] | None = None) -> Response:
    content, media_type, filename = exporters.render_many(report, formats, stem, extra)
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class ShareRequest(BaseModel):
    period: PeriodType = "monthly"
    reference_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    taluka_id: ObjectIdStr | None = None
    village_id: ObjectIdStr | None = None
    formats: list[ExportFormat] = Field(default_factory=lambda: ["pdf", "xlsx"], min_length=1)
    recipient_user_ids: list[ObjectIdStr] = Field(default_factory=list)
    recipient_emails: list[EmailStr] = Field(default_factory=list)


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=3)
    report_type: str | None = Field(None, description="Give either report_type or template_id")
    template_id: ObjectIdStr | None = None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly"]
    run_time: str = Field("07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Local time (IST)")
    formats: list[ExportFormat] = Field(default_factory=lambda: ["pdf"], min_length=1)
    taluka_id: ObjectIdStr | None = None
    village_id: ObjectIdStr | None = None
    recipient_user_ids: list[ObjectIdStr] = Field(default_factory=list)
    recipient_emails: list[EmailStr] = Field(default_factory=list)
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly"] | None = None
    run_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    formats: list[ExportFormat] | None = None
    recipient_user_ids: list[ObjectIdStr] | None = None
    recipient_emails: list[EmailStr] | None = None
    is_active: bool | None = None


@router.get("/types")
async def report_types(_: Stakeholder):
    return {"report_types": REPORT_TYPES, "periods": ["daily", "weekly", "monthly", "quarterly", "yearly", "custom"],
            "formats": ["json", *get_args(ExportFormat)], "format_labels": FORMAT_LABELS}


# ---------------------------------------------------------------- schedules & history (before /{report_type})

@router.get("/schedules")
async def list_schedules(db: Db, _: Stakeholder):
    return serialize(await db[c.REPORT_SCHEDULES].find().sort("name", 1).to_list())


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(body: ScheduleCreate, db: Db, actor: Stakeholder):
    if bool(body.report_type) == bool(body.template_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give exactly one of report_type or template_id")
    report_type = body.report_type
    if body.template_id:
        tpl = await get_or_404(db[c.REPORT_TEMPLATES], body.template_id, "Report template", {"is_active": True})
        report_type = tpl["report_type"]
    if report_type not in REPORT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown report type. Use one of {list(REPORT_TYPES)}")
    if not body.recipient_user_ids and not body.recipient_emails:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "At least one recipient is required")
    await validate_recipients(db, oids(body.recipient_user_ids), body.recipient_emails)
    now = utcnow()
    doc = {
        **body.model_dump(exclude={"taluka_id", "village_id", "recipient_user_ids", "template_id", "report_type"}),
        "report_type": report_type,
        "template_id": oid(body.template_id) if body.template_id else None,
        "taluka_id": oid(body.taluka_id) if body.taluka_id else None,
        "village_id": oid(body.village_id) if body.village_id else None,
        "recipient_user_ids": oids(body.recipient_user_ids),
        "next_run_at": next_run_after(body.frequency, today_local(), body.run_time),
        "last_run_at": None,
        "last_result": None,
        "created_by": actor["_id"],
        "created_at": now,
        "updated_at": now,
    }
    res = await db[c.REPORT_SCHEDULES].insert_one(doc)
    await audit.log(db, actor, "config_change", "report_schedule", res.inserted_id, f"Created report schedule '{body.name}'")
    return serialize(doc)


@router.patch("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleUpdate, db: Db, actor: Stakeholder):
    sch = await get_or_404(db[c.REPORT_SCHEDULES], schedule_id, "Schedule")
    updates = body.model_dump(exclude_unset=True)
    if "recipient_user_ids" in updates or "recipient_emails" in updates:
        user_ids = oids(updates.get("recipient_user_ids", [str(x) for x in sch["recipient_user_ids"]]))
        await validate_recipients(db, user_ids, updates.get("recipient_emails", sch["recipient_emails"]))
        if "recipient_user_ids" in updates:
            updates["recipient_user_ids"] = user_ids
    if "frequency" in updates or "run_time" in updates:
        updates["next_run_at"] = next_run_after(updates.get("frequency", sch["frequency"]), today_local(),
                                                updates.get("run_time", sch.get("run_time", "07:00")))
    updates["updated_at"] = utcnow()
    await db[c.REPORT_SCHEDULES].update_one({"_id": sch["_id"]}, {"$set": updates})
    await audit.log(db, actor, "config_change", "report_schedule", sch["_id"], f"Updated report schedule '{sch['name']}'")
    return serialize(await db[c.REPORT_SCHEDULES].find_one({"_id": sch["_id"]}))


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: str, db: Db, actor: Stakeholder):
    sch = await get_or_404(db[c.REPORT_SCHEDULES], schedule_id, "Schedule")
    await db[c.REPORT_SCHEDULES].delete_one({"_id": sch["_id"]})
    await audit.log(db, actor, "config_change", "report_schedule", sch["_id"], f"Deleted report schedule '{sch['name']}'")


@router.post("/schedules/{schedule_id}/run-now")
async def run_schedule_now(schedule_id: str, db: Db, actor: Stakeholder):
    sch = await get_or_404(db[c.REPORT_SCHEDULES], schedule_id, "Schedule")
    period = FREQUENCY_PERIOD[sch["frequency"]]
    start, end = previous_period(period, period_bounds(period, today_local())[0])
    try:
        out = await run_schedule(db, sch, start, end, actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    await db[c.REPORT_SCHEDULES].update_one({"_id": sch["_id"]}, {"$set": {
        "last_run_at": utcnow(), "last_result": {"status": "ok", "generated_report_id": out["_id"], "manual": True}}})
    return serialize(out)


@router.get("/generated")
async def generated_reports(db: Db, _: Stakeholder, pg: Pagination, report_type: str | None = None):
    query = {"report_type": report_type} if report_type else {}
    return await paginate(db[c.GENERATED_REPORTS], query, pg.page, pg.page_size, sort=[("created_at", -1)])


@router.get("/generated/{report_id}/download")
async def download_generated(report_id: str, db: Db, _: Stakeholder,
                             format: ExportFormat | Literal["attachment"] = "pdf", name: str | None = None):
    """format=attachment&name=<file name> downloads a template attachment sent with the report."""
    doc = await get_or_404(db[c.GENERATED_REPORTS], report_id, "Generated report")
    f = next((f for f in doc["files"] if f["format"] == format and (name is None or f.get("name") == name)), None)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {format} file for this report")
    path = (settings.reports_dir / f["path"]).resolve()
    if settings.reports_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "Report file is missing")
    return FileResponse(path, media_type=f["content_type"], filename=f.get("name") or path.name)


# ---------------------------------------------------------------- on-demand

@router.get("/{report_type}")
async def get_report(
    report_type: str,
    db: Db,
    actor: Stakeholder,
    period: PeriodType = "monthly",
    reference_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    taluka_id: ObjectIdStr | None = None,
    village_id: ObjectIdStr | None = None,
    format: Literal["json", "pdf", "xlsx", "csv", "docx"] = "json",
    formats: str | None = None,
):
    """Build a report for a period. format=pdf|xlsx|csv|docx downloads one file;
    formats=pdf,xlsx,... (comma-separated) downloads several, bundled as a ZIP."""
    chosen = parse_formats(formats, format)
    report = await build_report(db, report_type, period, reference_date, start_date, end_date,
                                oid(taluka_id) if taluka_id else None, oid(village_id) if village_id else None)
    if chosen is None:
        return serialize(report)
    await audit.log(db, actor, "export", "report", report_type, f"Exported {report_type} ({', '.join(chosen)})",
                    meta={"period": report["period"]["label"]})
    p = report["period"]
    return export_response(report, chosen, f"{report_type}_{p['start']:%Y%m%d}-{p['end']:%Y%m%d}")


@router.post("/{report_type}/share")
async def share_report(report_type: str, body: ShareRequest, db: Db, actor: Stakeholder):
    """Generate report files, store them, and share with authorised recipients."""
    if not body.recipient_user_ids and not body.recipient_emails:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "At least one recipient is required")
    out = await generate_and_share(
        db, report_type=report_type, period=body.period, reference=body.reference_date, start=body.start_date,
        end=body.end_date, formats=body.formats, taluka_id=oid(body.taluka_id) if body.taluka_id else None,
        village_id=oid(body.village_id) if body.village_id else None, recipient_user_ids=oids(body.recipient_user_ids),
        recipient_emails=body.recipient_emails, actor=actor)
    await audit.log(db, actor, "export", "report", out["_id"], f"Shared {report_type}",
                    meta={"recipients": len(out["recipient_user_ids"]) + len(out["recipient_emails"])})
    return serialize(out)
