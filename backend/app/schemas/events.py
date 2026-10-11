from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.master import GeoPoint
from app.utils.mongo import ObjectIdStr

TIME = r"^([01]\d|2[0-3]):[0-5]\d$"


class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    event_type: str = Field(description="event_type lookup code")
    objective: str | None = None
    village_id: ObjectIdStr
    location_name: str | None = Field(None, description="e.g. ZP school hall, Gram Panchayat office")
    location: GeoPoint | None = None
    event_date: date
    start_time: str = Field("10:00", pattern=TIME)
    end_time: str | None = Field(None, pattern=TIME)
    responsible_volunteer_id: ObjectIdStr | None = None
    expected_participants: int = Field(0, ge=0)
    group_ids: list[ObjectIdStr] = Field(default_factory=list, description="Kishori Groups invited")
    pre_checklist: list[str] | None = Field(None, description="Defaults from the event type if omitted")
    post_checklist: list[str] | None = None
    planned_budget: float | None = Field(None, ge=0)
    notify_participants: bool = Field(False, description="SMS reminder to invited girls' families the day before")
    is_historical: bool = Field(False, description="Back-dated entry of a past event")

    @model_validator(mode="after")
    def times(self):
        if self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    event_type: str | None = None
    objective: str | None = None
    location_name: str | None = None
    location: GeoPoint | None = None
    event_date: date | None = None
    start_time: str | None = Field(None, pattern=TIME)
    end_time: str | None = Field(None, pattern=TIME)
    responsible_volunteer_id: ObjectIdStr | None = None
    expected_participants: int | None = Field(None, ge=0)
    group_ids: list[ObjectIdStr] | None = None
    planned_budget: float | None = Field(None, ge=0)
    notify_participants: bool | None = None
    reschedule_reason: str | None = None


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3)


class ChecklistItem(BaseModel):
    item: str = Field(min_length=1)
    done: bool = False
    notes: str | None = None


class ChecklistUpdate(BaseModel):
    items: list[ChecklistItem]


class AttendanceEntry(BaseModel):
    girl_id: ObjectIdStr
    present: bool = True


class OtherParticipants(BaseModel):
    boys: int = Field(0, ge=0)
    parents: int = Field(0, ge=0)
    community_members: int = Field(0, ge=0)
    officials: int = Field(0, ge=0)
    others: int = Field(0, ge=0)


class AttendanceUpdate(BaseModel):
    entries: list[AttendanceEntry] = Field(default_factory=list)
    mark_groups_present: list[ObjectIdStr] = Field(
        default_factory=list, description="Shortcut: mark every girl of these groups present"
    )
    other_participants: OtherParticipants | None = None
    replace: bool = Field(False, description="Replace the whole attendance list instead of merging")


class EventReport(BaseModel):
    activities_conducted: str = Field(min_length=3)
    outcomes: str | None = None
    observations: str | None = None
    issues: str | None = None
    follow_up_actions: str | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None


class ExpenditureItem(BaseModel):
    item: str
    category: Literal["material", "refreshments", "travel", "venue", "honorarium", "printing", "medical", "other"] = "other"
    quantity: float = Field(1, ge=0)
    unit_cost: float = Field(0, ge=0)
    notes: str | None = None


class ExpenditureUpdate(BaseModel):
    items: list[ExpenditureItem]
    resources_used: list[str] = Field(default_factory=list, description="Non-monetary resources (projector, kits...)")
