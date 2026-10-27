from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    otp: str | None = Field(default=None, pattern=r"^\d{6}$")


class MFAConfirm(BaseModel):
    otp: str = Field(pattern=r"^\d{6}$")


class DoctorCreate(BaseModel):
    user_id: str
    specialty: str = Field(min_length=1, max_length=100)
    fee_paise: int = Field(ge=0, le=10000000)


class SlotCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timezone_required(cls, v):
        if v.tzinfo is None:
            raise ValueError("Timezone offset required")
        return v


class Booking(BaseModel):
    slot_id: str


class Transition(BaseModel):
    status: str = Field(pattern="^(in_progress|completed|cancelled)$")


class PrescriptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


# Explicit response contracts keep OpenAPI useful to frontend clients.
class IdOut(BaseModel):
    id: str


class UserOut(IdOut):
    role: str


class MeOut(UserOut):
    email: EmailStr
    name: str
    mfa_enabled: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str


class MFASetupOut(BaseModel):
    secret: str
    provisioning_uri: str


class EnabledOut(BaseModel):
    enabled: bool


class DoctorRefOut(BaseModel):
    doctor_id: str


class DoctorOut(IdOut):
    name: str
    specialty: str
    fee_paise: int


class SlotOut(IdOut):
    starts_at: datetime
    ends_at: datetime


class BookingOut(IdOut):
    status: str


class ConsultationOut(BookingOut):
    patient_id: str
    doctor_id: str
    slot_id: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    doctor_name: str | None = None
    patient_name: str | None = None


class PrescriptionRefOut(BaseModel):
    consultation_id: str


class PrescriptionOut(PrescriptionRefOut):
    text: str


class AnalyticsOut(BaseModel):
    consultations_by_status: dict[str, int]
    patients: int
    doctors: int


class AuditOut(IdOut):
    actor_id: str
    action: str
    resource_id: str
    created_at: datetime


class HealthOut(BaseModel):
    status: str
