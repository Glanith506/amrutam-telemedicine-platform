import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(12), default="patient")
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[int] = mapped_column(Integer, default=0)
    last_totp: Mapped[int] = mapped_column(Integer, default=-1)
    __table_args__ = (CheckConstraint("role in ('patient','doctor','admin')"),)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class Doctor(Base):
    __tablename__ = "doctors"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    specialty: Mapped[str] = mapped_column(String(100), index=True)
    fee_paise: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("fee_paise >= 0"),)


class Slot(Base):
    __tablename__ = "availability_slots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.user_id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("doctor_id", "starts_at"),
        CheckConstraint("ends_at > starts_at"),
    )


class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.user_id"), index=True)
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("availability_slots.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="booked", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("status in ('booked','in_progress','completed','cancelled')"),
    )


Index(
    "uq_active_slot",
    Consultation.slot_id,
    unique=True,
    postgresql_where=Consultation.status != "cancelled",
    sqlite_where=Consultation.status != "cancelled",
)


class Prescription(Base):
    __tablename__ = "prescriptions"
    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), primary_key=True
    )
    encrypted_text: Mapped[str] = mapped_column(Text)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), unique=True
    )
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    __table_args__ = (CheckConstraint("amount_paise >= 0"),)


class Audit(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )


class Idempotency(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[str] = mapped_column(Text)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
