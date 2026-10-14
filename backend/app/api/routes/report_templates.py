"""Saved report templates (PRD 4.18 "report templates").

A template fixes a report type plus its default period and scope, and chooses which
summary items, sections and columns appear (and in what order), with an optional
custom title and notes. Templates can be run, exported, shared and scheduled.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from app.core.deps import Db, Stakeholder
from app.db import collections as c
from app.api.routes.reports import export_response, parse_formats
from app.services import audit, template_attachments
from app.services.exporters import ExportFormat
from app.services.report_delivery import generate_and_share
from app.services.reports import REPORT_TYPES, apply_template, build_report, report_structure, validate_template_against
from app.utils.dates import PeriodType, utcnow
from app.utils.mongo import ObjectIdStr, diff, get_or_404, oid, oids, serialize

router = APIRouter(prefix="/reports", tags=["report templates"])


class SectionSelection(BaseModel):
    key: str = Field(description="Section key from GET /reports/types/{report_type}/structure")
    title: str | None = Field(None, description="Rename the section")
    columns: list[str] | None = Field(None, description="Column keys to keep, in order (default: all)")


class TemplateBase(BaseModel):
    description: str | None = None
    default_period: PeriodType | None = None
    taluka_id: ObjectIdStr | None = None
    village_id: ObjectIdStr | None = None
    title: str | None = Field(None, description="Custom report title")
    subtitle_note: str | None = Field(None, description="Extra line shown under the scope, e.g. 'For donor: XYZ Trust'")
    include_summary: bool | None = None
    summary_labels: list[str] | None = Field(None, description="Summary items to keep, in order (default: all)")
    sections: list[SectionSelection] | None = Field(None, description="Sections to include, in order (default: all)")
    notes: list[str] | None = None
    append_default_notes: bool | None = None
    default_formats: list[ExportFormat] | None = None


class TemplateCreate(TemplateBase):
    name: str = Field(min_length=3, max_length=120)
    report_type: str
    default_period: PeriodType = "monthly"
    include_summary: bool = True
    append_default_notes: bool = True
    default_formats: list[ExportFormat] = Field(default_factory=lambda: ["pdf"], min_length=1)


class TemplateUpdate(TemplateBase):
    name: str | None = Field(None, min_length=3, max_length=120)
    is_active: bool | None = None


class TemplateShare(BaseModel):
    period: PeriodType | None = None
    reference_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    formats: list[ExportFormat] | None = None
    recipient_user_ids: list[ObjectIdStr] = Field(default_factory=list)
    recipient_emails: list[EmailStr] = Field(default_factory=list)


async def _structure(db, report_type: str) -> dict:
    if report_type not in REPORT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown report type. Use one of {list(REPORT_TYPES)}")
    return report_structure(await build_report(db, report_type, "monthly"))


async def _validate(db, tpl: dict) -> None:
    errors = validate_template_against(await _structure(db, tpl["report_type"]), tpl)
    if tpl.get("village_id"):
        village = await get_or_404(db[c.VILLAGES], tpl["village_id"], "Village")
        if tpl.get("taluka_id") and village["taluka_id"] != tpl["taluka_id"]:
            errors.append("village_id is not in taluka_id")
    if tpl.get("taluka_id"):
        await get_or_404(db[c.TALUKAS], tpl["taluka_id"], "Taluka")
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"validation_errors": errors})


def _prepare(data: dict) -> dict:
    for k in ("taluka_id", "village_id"):
        if k in data:
            data[k] = oid(data[k]) if data[k] else None
    if data.get("sections") is not None:
        data["sections"] = [s if isinstance(s, dict) else s.model_dump() for s in data["sections"]]
    return data


@router.get("/types/{report_type}/structure")
async def structure(report_type: str, db: Db, _: Stakeholder):
    """Sections, columns and summary items available for building a template."""
    return await _structure(db, report_type)


@router.get("/templates")
async def list_templates(db: Db, _: Stakeholder, report_type: str | None = None, include_inactive: bool = False):
    query: dict = {} if include_inactive else {"is_active": True}
    if report_type:
        query["report_type"] = report_type
    return serialize(await db[c.REPORT_TEMPLATES].find(query).sort("name", 1).to_list())


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(body: TemplateCreate, db: Db, actor: Stakeholder):
    doc = _prepare(body.model_dump())
    await _validate(db, doc)
    now = utcnow()
    doc.update(is_active=True, created_by=actor["_id"], created_at=now, updated_at=now)
    try:
        res = await db[c.REPORT_TEMPLATES].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A template with this name already exists")
    await audit.log(db, actor, "config_change", "report_template", res.inserted_id, f"Created report template '{body.name}'")
    return serialize(doc)


@router.get("/templates/{template_id}")
async def get_template(template_id: str, db: Db, _: Stakeholder):
    return serialize(await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template"))


@router.patch("/templates/{template_id}")
async def update_template(template_id: str, body: TemplateUpdate, db: Db, actor: Stakeholder):
    before = await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template")
    updates = _prepare(body.model_dump(exclude_unset=True))
    if not updates:
        return serialize(before)
    await _validate(db, {**before, **updates})
    updates["updated_at"] = utcnow()
    try:
        await db[c.REPORT_TEMPLATES].update_one({"_id": before["_id"]}, {"$set": updates})
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A template with this name already exists")
    after = await db[c.REPORT_TEMPLATES].find_one({"_id": before["_id"]})
    await audit.log(db, actor, "config_change", "report_template", before["_id"],
                    f"Updated report template '{after['name']}'", diff(before, after))
    return serialize(after)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_template(template_id: str, db: Db, actor: Stakeholder):
    tpl = await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template")
    in_use = await db[c.REPORT_SCHEDULES].count_documents({"template_id": tpl["_id"], "is_active": True})
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Template is used by {in_use} active schedule(s); deactivate them first")
    await db[c.REPORT_TEMPLATES].update_one({"_id": tpl["_id"]}, {"$set": {"is_active": False, "updated_at": utcnow()}})
    await audit.log(db, actor, "config_change", "report_template", tpl["_id"], f"Deactivated report template '{tpl['name']}'")


@router.get("/templates/{template_id}/run")
async def run_template(
    template_id: str,
    db: Db,
    actor: Stakeholder,
    period: PeriodType | None = None,
    reference_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    format: Literal["json", "pdf", "xlsx", "csv", "docx"] = "json",
    formats: str | None = Query(None, description="Comma-separated, e.g. pdf,xlsx; several are bundled as a ZIP"),
):
    """Build the report defined by a template. Period defaults to the template's default period."""
    tpl = await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template", {"is_active": True})
    report = await build_report(db, tpl["report_type"], period or tpl["default_period"], reference_date, start_date,
                                end_date, tpl.get("taluka_id"), tpl.get("village_id"))
    report = apply_template(report, tpl)
    chosen = parse_formats(formats, format)
    if chosen is None:
        return serialize(report)
    await audit.log(db, actor, "export", "report_template", tpl["_id"],
                    f"Exported template '{tpl['name']}' ({', '.join(chosen)})", meta={"period": report["period"]["label"]})
    p = report["period"]
    safe = "".join(ch if ch.isalnum() else "_" for ch in tpl["name"])[:40]
    return export_response(report, chosen, f"{safe}_{p['start']:%Y%m%d}-{p['end']:%Y%m%d}",
                           template_attachments.load_all(tpl))


@router.post("/templates/{template_id}/share")
async def share_template(template_id: str, body: TemplateShare, db: Db, actor: Stakeholder):
    tpl = await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template", {"is_active": True})
    if not body.recipient_user_ids and not body.recipient_emails:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "At least one recipient is required")
    out = await generate_and_share(
        db, report_type=tpl["report_type"], period=body.period or tpl["default_period"], reference=body.reference_date,
        start=body.start_date, end=body.end_date, formats=body.formats or tpl["default_formats"],
        taluka_id=tpl.get("taluka_id"), village_id=tpl.get("village_id"),
        recipient_user_ids=oids(body.recipient_user_ids), recipient_emails=body.recipient_emails,
        actor=actor, template=tpl)
    await audit.log(db, actor, "export", "report_template", tpl["_id"], f"Shared template '{tpl['name']}'",
                    meta={"generated_report_id": out["_id"]})
    return serialize(out)


# ---------------------------------------------------------------- attachments (PDF / Word sent with every report)

@router.post("/templates/{template_id}/attachments", status_code=status.HTTP_201_CREATED)
async def add_attachment(template_id: str, db: Db, actor: Stakeholder, file: UploadFile = File(...)):
    tpl = await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template", {"is_active": True})
    entry = await template_attachments.save(file, tpl.get("attachments") or [], actor)
    await db[c.REPORT_TEMPLATES].update_one({"_id": tpl["_id"]}, {"$push": {"attachments": entry},
                                                                  "$set": {"updated_at": utcnow()}})
    await audit.log(db, actor, "config_change", "report_template", tpl["_id"],
                    f"Attached '{entry['original_name']}' to report template '{tpl['name']}'")
    return serialize(entry)


async def _attachment(db, template_id: str, attachment_id: str) -> tuple[dict, dict]:
    tpl = await get_or_404(db[c.REPORT_TEMPLATES], template_id, "Report template")
    entry = next((a for a in tpl.get("attachments") or [] if a["id"] == attachment_id), None)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    return tpl, entry


@router.get("/templates/{template_id}/attachments/{attachment_id}")
async def download_attachment(template_id: str, attachment_id: str, db: Db, _: Stakeholder):
    _, entry = await _attachment(db, template_id, attachment_id)
    path = template_attachments.file_path(entry)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "Attachment file is missing")
    return FileResponse(path, media_type=entry["content_type"], filename=entry["original_name"])


@router.delete("/templates/{template_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(template_id: str, attachment_id: str, db: Db, actor: Stakeholder):
    tpl, entry = await _attachment(db, template_id, attachment_id)
    await db[c.REPORT_TEMPLATES].update_one({"_id": tpl["_id"]}, {"$pull": {"attachments": {"id": attachment_id}},
                                                                  "$set": {"updated_at": utcnow()}})
    # Reports already generated keep their own copy, so the template's file can go.
    template_attachments.file_path(entry).unlink(missing_ok=True)
    await audit.log(db, actor, "config_change", "report_template", tpl["_id"],
                    f"Removed '{entry['original_name']}' from report template '{tpl['name']}'")
