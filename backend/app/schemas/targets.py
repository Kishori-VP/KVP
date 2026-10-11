from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.utils.dates import PeriodType
from app.utils.mongo import ObjectIdStr


class TargetCreate(BaseModel):
    volunteer_ids: list[ObjectIdStr] = Field(default_factory=list)
    all_active_volunteers: bool = Field(False, description="Assign to every active volunteer")
    target_type: str = Field(description="target_type lookup code")
    period_type: PeriodType
    reference_date: date | None = Field(None, description="Any date inside the first period (default: today)")
    period_start: date | None = Field(None, description="Required for custom periods")
    period_end: date | None = Field(None, description="Required for custom periods")
    periods: int = Field(1, ge=1, le=24, description="Create targets for this many consecutive periods")
    target_value: int = Field(gt=0)
    title: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check(self):
        if not self.volunteer_ids and not self.all_active_volunteers:
            raise ValueError("Give volunteer_ids or set all_active_volunteers=true")
        if self.period_type == "custom":
            if not (self.period_start and self.period_end):
                raise ValueError("Custom targets need period_start and period_end")
            if self.period_end < self.period_start:
                raise ValueError("period_end must be on or after period_start")
            if self.periods != 1:
                raise ValueError("Custom targets cannot repeat")
        return self


class TargetRevise(BaseModel):
    target_value: int | None = Field(None, gt=0)
    period_end: date | None = None
    title: str | None = None
    notes: str | None = None
    reason: str = Field(min_length=3)


class TargetCancel(BaseModel):
    reason: str = Field(min_length=3)
