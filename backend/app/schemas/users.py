from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.permissions import Role
from app.utils.mongo import ObjectIdStr

PHONE_PATTERN = r"^[6-9]\d{9}$"


class LoginRequest(BaseModel):
    identifier: str = Field(description="Email address or 10-digit mobile number")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ContactDetails(BaseModel):
    alternate_phone: str | None = Field(None, pattern=PHONE_PATTERN)
    address: str | None = None
    whatsapp: str | None = None


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str = Field(pattern=PHONE_PATTERN)
    password: str = Field(min_length=8)
    role: Role
    village_id: ObjectIdStr | None = Field(
        None, description="Optional for Volunteers: a volunteer has at most one village and can be assigned later"
    )
    group_ids: list[ObjectIdStr] = Field(default_factory=list, description="Kishori Groups in the assigned village")
    assignment_start_date: date | None = None
    contact: ContactDetails = Field(default_factory=ContactDetails)
    designation: str | None = None
    is_active: bool = True

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_to_none(cls, v):
        return v or None

    @model_validator(mode="after")
    def check_village_rule(self):
        if self.group_ids and not self.village_id:
            raise ValueError("Groups can only be assigned together with a village")
        if self.role == Role.STAKEHOLDER and (self.village_id or self.group_ids):
            raise ValueError("Stakeholders are not mapped to a village")
        return self


class UserUpdate(BaseModel):
    """Profile fields. Village changes go through /volunteers/{id}/reassign."""

    name: str | None = Field(None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(None, pattern=PHONE_PATTERN)
    contact: ContactDetails | None = None
    designation: str | None = None


class RoleChange(BaseModel):
    role: Role
    village_id: ObjectIdStr | None = Field(None, description="Optional village when changing to Volunteer")
    reason: str | None = None


class StatusChange(BaseModel):
    is_active: bool
    reason: str | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


class TargetHandling(BaseModel):
    action: str = Field(
        "move",
        pattern="^(move|close|transfer)$",
        description="What happens to the volunteer's open targets: move to new village, close them, "
        "or transfer them to another volunteer who stays in the old village",
    )
    transfer_to_volunteer_id: ObjectIdStr | None = None


class ReassignRequest(BaseModel):
    village_id: ObjectIdStr
    group_ids: list[ObjectIdStr] = Field(default_factory=list)
    effective_date: date | None = None
    reason: str = Field(min_length=3)
    targets: TargetHandling = Field(default_factory=TargetHandling)

    @model_validator(mode="after")
    def check_transfer(self):
        if self.targets.action == "transfer" and not self.targets.transfer_to_volunteer_id:
            raise ValueError("transfer_to_volunteer_id is required when targets.action is 'transfer'")
        return self


class AssignRequest(BaseModel):
    """First village assignment for a volunteer who has none."""

    village_id: ObjectIdStr
    group_ids: list[ObjectIdStr] = Field(default_factory=list)
    effective_date: date | None = None


class GroupAssignment(BaseModel):
    group_ids: list[ObjectIdStr]
