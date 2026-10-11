from typing import Literal

from pydantic import BaseModel, Field

from app.utils.mongo import ObjectIdStr


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class TalukaCreate(BaseModel):
    name: str = Field(min_length=2)
    name_mr: str | None = None
    district: str = Field(min_length=2)
    district_mr: str | None = None
    state: str = "Maharashtra"
    is_active: bool = True


class TalukaUpdate(BaseModel):
    name: str | None = None
    name_mr: str | None = None
    district: str | None = None
    district_mr: str | None = None
    state: str | None = None
    is_active: bool | None = None


class VillageCreate(BaseModel):
    name: str = Field(min_length=2, description="English name")
    name_mr: str | None = Field(None, description="Marathi name")
    taluka_id: ObjectIdStr
    pin_code: str | None = Field(None, pattern=r"^\d{6}$")
    location: GeoPoint | None = None
    hamlets: list[str] = Field(default_factory=list, description="Hamlets/wadis covered under this village")
    aliases: list[str] = Field(default_factory=list, description="Alternate spellings, used for data import")
    status: Literal["active", "inactive"] = "active"


class VillageUpdate(BaseModel):
    name: str | None = None
    name_mr: str | None = None
    taluka_id: ObjectIdStr | None = None
    pin_code: str | None = Field(None, pattern=r"^\d{6}$")
    location: GeoPoint | None = None
    hamlets: list[str] | None = None
    aliases: list[str] | None = None
    status: Literal["active", "inactive"] | None = None


class MeetingSchedule(BaseModel):
    frequency: Literal["weekly", "fortnightly", "monthly", "custom"] = "monthly"
    day_of_week: int | None = Field(None, ge=0, le=6, description="Monday=0")
    week_of_month: int | None = Field(None, ge=1, le=5)
    time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    notes: str | None = None


GroupType = Literal["kishori", "bal_panchayat"]


class GroupCreate(BaseModel):
    name: str = Field(min_length=1)
    group_type: GroupType = "kishori"
    group_number: str | None = None
    village_id: ObjectIdStr
    meeting_schedule: MeetingSchedule | None = None
    responsible_volunteer_id: ObjectIdStr | None = None
    is_active: bool = True


class GroupUpdate(BaseModel):
    name: str | None = None
    group_number: str | None = None
    meeting_schedule: MeetingSchedule | None = None
    responsible_volunteer_id: ObjectIdStr | None = None
    is_active: bool | None = None


class ContactCreate(BaseModel):
    village_id: ObjectIdStr
    category: str = Field(description="contact_category lookup code, e.g. sarpanch, talathi")
    name: str = Field(min_length=2)
    designation: str | None = None
    facility_name: str | None = Field(None, description="For hospital/clinic contacts")
    mobile: str
    alternate_mobile: str | None = None
    availability: str | None = Field(None, description="e.g. 'Mon-Sat 10am-5pm'")
    notes: str | None = None


class ContactUpdate(BaseModel):
    category: str | None = None
    name: str | None = None
    designation: str | None = None
    facility_name: str | None = None
    mobile: str | None = None
    alternate_mobile: str | None = None
    availability: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class VillageLocationItem(BaseModel):
    village_id: ObjectIdStr
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    pin_code: str | None = Field(None, pattern=r"^\d{6}$")


class VillageLocationsUpdate(BaseModel):
    items: list[VillageLocationItem] = Field(min_length=1, max_length=500)
