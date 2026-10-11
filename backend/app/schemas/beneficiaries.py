from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.master import GeoPoint
from app.utils.mongo import ObjectIdStr

EnrollmentStatus = Literal["active", "inactive", "migrated", "married", "exited"]
Severity = Literal["critical", "high", "medium", "low"]
CaseStatus = Literal["open", "in_progress", "escalated", "resolved", "closed"]


class Household(BaseModel):
    head_name: str | None = None
    father_name: str | None = None
    mother_name: str | None = None
    guardian_name: str | None = None
    phone: str | None = Field(None, pattern=r"^[6-9]\d{9}$")
    address: str | None = None
    hamlet: str | None = None
    members_count: int | None = Field(None, ge=1, le=50)
    father_occupation: str | None = None
    mother_occupation: str | None = None
    economic_status: Literal["bpl", "apl", "unknown"] | None = None
    social_category: str | None = None
    notes: str | None = None


class Enrollment(BaseModel):
    status: EnrollmentStatus = "active"
    enrolled_on: date | None = None
    exit_reason: str | None = None


class GirlBase(BaseModel):
    name: str | None = Field(None, max_length=150)
    dob: date | None = None
    age: int | None = Field(None, ge=5, le=30, description="Use when date of birth is unknown")
    village_id: ObjectIdStr | None = None
    group_id: ObjectIdStr | None = None
    school_status: str | None = Field(None, description="school_status lookup code")
    school_name: str | None = None
    standard: str | None = Field(None, description="Class / standard")
    household: Household | None = None
    enrollment: Enrollment | None = None
    phone: str | None = Field(None, pattern=r"^[6-9]\d{9}$")
    custom_fields: dict[str, Any] | None = None


class GirlCreate(GirlBase):
    village_id: ObjectIdStr
    name: str = Field(min_length=2, max_length=150)
    survey_date: date | None = None
    confirm_not_duplicate: bool = Field(
        False, description="Set true to save even though possible duplicates were found"
    )

    @model_validator(mode="after")
    def dob_not_future(self):
        if self.dob and self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return self


class GirlUpdate(GirlBase):
    pass


class DuplicateCheck(BaseModel):
    name: str | None = None
    village_id: ObjectIdStr | None = None
    age: int | None = None
    dob: date | None = None
    group_id: ObjectIdStr | None = None
    household: Household | None = None
    exclude_id: ObjectIdStr | None = None


class MergeRequest(BaseModel):
    duplicate_id: ObjectIdStr
    reason: str = Field(min_length=3)


class HealthRecordCreate(BaseModel):
    recorded_on: date
    hb_level: float | None = Field(None, ge=2, le=20, description="Haemoglobin g/dL")
    weight_kg: float | None = Field(None, ge=10, le=150)
    height_cm: float | None = Field(None, ge=80, le=200)
    observations: dict[str, Any] = Field(default_factory=dict, description="Values for configured health fields")
    source: Literal["health_camp", "home_visit", "event", "school", "phc", "other"] = "other"
    event_id: ObjectIdStr | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def not_future(self):
        if self.recorded_on > date.today():
            raise ValueError("recorded_on cannot be in the future")
        return self


class CaseCreate(BaseModel):
    girl_id: ObjectIdStr
    category: str = Field(description="case_category lookup code")
    severity: Severity
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    source_type: Literal["home_visit", "event", "profile", "other"] = "profile"
    source_id: ObjectIdStr | None = None
    assigned_to: ObjectIdStr | None = None
    due_date: date | None = None
    next_action: str | None = None
    sensitive: bool = True


class CaseUpdate(BaseModel):
    category: str | None = None
    severity: Severity | None = None
    title: str | None = None
    description: str | None = None
    due_date: date | None = None
    next_action: str | None = None
    sensitive: bool | None = None


class CaseNote(BaseModel):
    type: Literal["note", "follow_up", "visit", "call", "referral"] = "note"
    text: str = Field(min_length=1)
    media_ids: list[ObjectIdStr] = Field(default_factory=list)
    next_action: str | None = None


class CaseStatusChange(BaseModel):
    status: CaseStatus
    note: str = Field(min_length=3, description="Reason / resolution summary (required)")


class CaseAssign(BaseModel):
    assigned_to: ObjectIdStr
    due_date: date | None = None
    next_action: str | None = None


class GpsCapture(GeoPoint):
    accuracy_m: float | None = Field(None, ge=0)
    captured_at: str | None = None


class RiskIndicators(BaseModel):
    child_marriage_risk: bool = False
    school_dropout_risk: bool = False
    health_concern: bool = False
    anaemia_concern: bool = False
    gender_discrimination: bool = False
    other: str | None = None


class HomeVisitCreate(BaseModel):
    volunteer_id: ObjectIdStr
    visit_date: date
    girl_ids: list[ObjectIdStr] = Field(default_factory=list)
    purpose: Literal["routine", "follow_up", "case_follow_up", "enrolment", "other"] = "routine"
    status: Literal["planned", "completed", "missed"] = "completed"
    met_with: list[str] = Field(default_factory=list, description="girl, mother, father, guardian...")
    observations: str | None = None
    family_info: dict[str, Any] | None = None
    risk_indicators: RiskIndicators | None = None
    gps: GpsCapture | None = None
    is_historical: bool = False
    notes: str | None = None


class HomeVisitUpdate(BaseModel):
    visit_date: date | None = None
    girl_ids: list[ObjectIdStr] | None = None
    purpose: Literal["routine", "follow_up", "case_follow_up", "enrolment", "other"] | None = None
    status: Literal["planned", "completed", "missed"] | None = None
    met_with: list[str] | None = None
    observations: str | None = None
    family_info: dict[str, Any] | None = None
    risk_indicators: RiskIndicators | None = None
    notes: str | None = None


class ActivityReportCreate(BaseModel):
    """Daily activity report (digital version of the existing Google Form)."""

    volunteer_id: ObjectIdStr
    report_date: date
    activities: list[str] = Field(description="activity_type lookup codes done that day")
    group_ids: list[ObjectIdStr] = Field(default_factory=list, description="Groups met")
    girls_present: int = Field(0, ge=0)
    topics_discussed: str | None = None
    home_visits_count: int = Field(0, ge=0)
    home_visit_girl_ids: list[ObjectIdStr] = Field(default_factory=list)
    other_meetings: str | None = Field(None, description="Others met and information received")
    is_historical: bool = False


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    remarks: str | None = None
