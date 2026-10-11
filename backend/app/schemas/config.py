from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.permissions import ACTIONS, RESOURCES, STAKEHOLDER_ONLY


class LookupCreate(BaseModel):
    type: str
    code: str = Field(pattern=r"^[a-z0-9_]+$", min_length=2, max_length=60)
    label: str
    label_mr: str | None = None
    description: str | None = None
    order: int = 0
    is_active: bool = True
    # Free-form attributes per lookup type, e.g. {"metric": "home_visits"} for target types,
    # {"data_type": "number", "unit": "g/dL"} for health fields, {"is_meeting": true} for event types.
    attributes: dict[str, Any] = Field(default_factory=dict)


class LookupUpdate(BaseModel):
    label: str | None = None
    label_mr: str | None = None
    description: str | None = None
    order: int | None = None
    is_active: bool | None = None
    attributes: dict[str, Any] | None = None


class TargetThresholds(BaseModel):
    on_track_min_ratio: float = Field(ge=0, le=1.5)
    low_performance_ratio: float = Field(ge=0, le=1)
    deadline_warning_days: int = Field(ge=0, le=60)


class EscalationRules(BaseModel):
    case_due_days_by_severity: dict[Literal["critical", "high", "medium", "low"], int]
    case_no_update_days: int = Field(ge=1)
    escalate_after_overdue_days: int = Field(ge=0)
    auto_escalate: bool = False


class VillageStatusRules(BaseModel):
    on_track_within_days: int = Field(ge=1)
    delayed_within_days: int = Field(ge=1)

    @model_validator(mode="after")
    def order(self):
        if self.delayed_within_days < self.on_track_within_days:
            raise ValueError("delayed_within_days must be >= on_track_within_days")
        return self


class DuplicateMatching(BaseModel):
    fields: list[Literal["name", "village_id", "age", "dob", "household.father_name", "household.mother_name",
                        "household.head_name", "household.phone", "group_id"]]
    name_similarity_threshold: float = Field(ge=0.5, le=1)
    age_tolerance_years: int = Field(ge=0, le=5)
    min_score: float = Field(ge=0.1, le=1)


class GirlIdFormat(BaseModel):
    prefix: str = Field(min_length=1, max_length=20)
    pad: int = Field(ge=0, le=8)


class AnaemiaThresholds(BaseModel):
    severe_below: float
    moderate_below: float
    mild_below: float

    @model_validator(mode="after")
    def order(self):
        if not (self.severe_below < self.moderate_below < self.mild_below):
            raise ValueError("Thresholds must satisfy severe < moderate < mild")
        return self


class ReportingRules(BaseModel):
    expected_activity_report: Literal["daily", "weekly", "none"]
    working_days: list[int] = Field(description="Monday=0 ... Sunday=6")
    grace_days: int = Field(ge=0, le=14)


class EntityRules(BaseModel):
    required: list[str] = Field(default_factory=list)
    rules: dict[str, dict[str, Any]] = Field(default_factory=dict)


class VolunteerPermissions(BaseModel):
    volunteer: dict[str, list[str]]

    @model_validator(mode="after")
    def check(self):
        for resource, actions in self.volunteer.items():
            if resource not in RESOURCES:
                raise ValueError(f"Unknown resource '{resource}'")
            if resource in STAKEHOLDER_ONLY and actions:
                raise ValueError(f"'{resource}' is Stakeholder-only and cannot be granted to Volunteers")
            bad = set(actions) - set(ACTIONS)
            if bad:
                raise ValueError(f"Unknown actions {sorted(bad)} for '{resource}'")
        return self


class MessagingRules(BaseModel):
    participant_reminders_enabled: bool
    participant_reminder_template: str = Field(min_length=10, max_length=500,
                                               description="Placeholders: {title} {date} {time} {place}")

    @model_validator(mode="after")
    def placeholders(self):
        try:
            self.participant_reminder_template.format(title="t", date="d", time="h", place="p")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"Template has an unknown placeholder: {exc}")
        return self


class ReportSharing(BaseModel):
    allowed_external_emails: list[EmailStr] = Field(default_factory=list)


SETTING_SCHEMAS: dict[str, type[BaseModel] | None] = {
    "target_thresholds": TargetThresholds,
    "escalation_rules": EscalationRules,
    "village_status": VillageStatusRules,
    "duplicate_matching": DuplicateMatching,
    "girl_id": GirlIdFormat,
    "anaemia_thresholds": AnaemiaThresholds,
    "reporting": ReportingRules,
    "validation_rules": None,  # validated as dict[str, EntityRules] in the route
    "permissions": VolunteerPermissions,
    "report_sharing": ReportSharing,
    "messaging": MessagingRules,
}

ProviderType = Literal["ocr", "speech_to_text", "llm", "translation", "sms", "email", "maps", "push"]


class ProviderConfigUpsert(BaseModel):
    provider_type: ProviderType
    provider_name: str = Field(min_length=2, description="e.g. bhashini, google, azure, anthropic")
    is_active: bool = False
    is_default: bool = False
    config: dict[str, Any] = Field(default_factory=dict, description="Non-secret settings (endpoint, model, language)")
    credentials: dict[str, str] | None = Field(
        None, description="Secret values (API keys). Stored encrypted, never returned. Omit to keep existing."
    )
