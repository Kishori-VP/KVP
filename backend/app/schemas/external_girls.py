from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, Field

from app.utils.dates import today_local
from app.utils.mongo import ObjectIdStr

CallStatus = Literal["completed", "planned", "unanswered", "busy", "wrong_number"]
CallPurpose = Literal["routine", "follow_up", "case_follow_up", "enrolment", "health", "counseling", "other"]
GirlStatus = Literal["active", "follow_up", "closed"]


class ExternalGirlCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    name_en: str | None = None
    phone: str | None = Field(None, max_length=15)
    alt_phone: str | None = None
    age: int | None = Field(None, ge=5, le=45)
    dob: date | None = None
    location: str | None = Field(None, max_length=200)
    guardian_name: str | None = Field(None, max_length=150)
    guardian_relation: str | None = Field(None, max_length=50)
    education_status: str | None = Field(None, max_length=100)
    school_or_college: str | None = Field(None, max_length=200)
    standard: str | None = Field(None, max_length=50)
    status: GirlStatus = "active"
    notes: str | None = None


class ExternalGirlUpdate(BaseModel):
    name: str | None = None
    name_en: str | None = None
    phone: str | None = None
    alt_phone: str | None = None
    age: int | None = None
    dob: date | None = None
    location: str | None = None
    guardian_name: str | None = None
    guardian_relation: str | None = None
    education_status: str | None = None
    school_or_college: str | None = None
    standard: str | None = None
    status: GirlStatus | None = None
    notes: str | None = None


class ExternalCallCreate(BaseModel):
    external_girl_id: ObjectIdStr
    call_date: date = Field(default_factory=today_local)
    status: CallStatus = "completed"
    purpose: CallPurpose = "routine"
    phone_called: str | None = None
    duration_minutes: int | None = Field(None, ge=0, le=300)
    risk_indicators: dict[str, Any] | None = None
    observations: str | None = None
    notes: str | None = None


class ExternalCallUpdate(BaseModel):
    call_date: date | None = None
    status: CallStatus | None = None
    purpose: CallPurpose | None = None
    phone_called: str | None = None
    duration_minutes: int | None = None
    risk_indicators: dict[str, Any] | None = None
    observations: str | None = None
    notes: str | None = None
