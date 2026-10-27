import json, logging, time, uuid
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query
from fastapi.responses import Response, JSONResponse
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from app.db import get_db
from app.models import (
    User,
    Profile,
    Doctor,
    Slot,
    Consultation,
    Prescription,
    Payment,
    Audit,
    Outbox,
)
from app.schemas import (
    Register,
    Login,
    MFAConfirm,
    DoctorCreate,
    SlotCreate,
    Booking,
    Transition,
    PrescriptionCreate,
)
from app.security import (
    passwords,
    token,
    current_user,
    role,
    encrypt,
    decrypt,
    verify_otp,
)
from app.schemas import (
    IdOut,
    UserOut,
    MeOut,
    TokenOut,
    MFASetupOut,
    EnabledOut,
    DoctorRefOut,
    DoctorOut,
    SlotOut,
    BookingOut,
    ConsultationOut,
    PrescriptionRefOut,
    PrescriptionOut,
    AnalyticsOut,
    AuditOut,
    HealthOut,
)
from app.services import audit, lock, rate_limit, write
from app.config import settings
import pyotp

app = FastAPI(title="Amrutam Telemedicine API", version="1.1.0")
static_directory = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/assets", StaticFiles(directory=static_directory), name="assets")


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(
        static_directory / "index.html",
        headers={
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        },
    )


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("amrutam")
REQUESTS = Counter("http_requests_total", "Requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Latency", ["method", "route"])
if settings.otel_exporter_otlp_endpoint:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
            )
        )
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls="health/live,health/ready,metrics"
    )


@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception:
        log.error(json.dumps({"event": "unhandled_error", "request_id": request_id}))
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    route = getattr(request.scope.get("route"), "path", "unmatched")
    elapsed = time.perf_counter() - started
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(elapsed)
    log.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "route": route,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
            }
        )
    )
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
    )
    return response


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": "Resource conflicts with an existing record"},
    )


@app.get("/health/live", response_model=HealthOut)
def live():
    return {"status": "ok"}


@app.get("/health/ready", response_model=HealthOut)
def ready(db=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Database unavailable")
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# All domain writes require a client-generated key. Response and mutation share one transaction.
limited = [Depends(rate_limit)]


@app.post(
    "/auth/register", dependencies=limited, status_code=201, response_model=UserOut
)
def register(
    body: Register,
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    def run():
        user = User(
            email=str(body.email).lower(),
            password_hash=passwords.hash(body.password),
            role="patient",
        )
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id, name=body.name))
        audit(db, user, "registered", user.id)
        return {"id": user.id, "role": user.role}

    return write(db, str(body.email).lower(), key, "register", body.model_dump(), run)


@app.post("/auth/login", dependencies=limited, response_model=TokenOut)
def login(body: Login, db=Depends(get_db)):
    user = db.scalar(
        select(User).where(User.email == str(body.email).lower()).with_for_update()
    )
    if not user:
        passwords.hash(body.password)
        raise HTTPException(401, "Invalid credentials")
    if not passwords.verify(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    mfa = False
    if user.mfa_enabled:
        verify_otp(user, body.otp)
        mfa = True
    elif user.role in ("doctor", "admin"):
        raise HTTPException(403, "Set up MFA before assigning a privileged role")
    audit(db, user, "login", user.id)
    db.commit()
        # "bearer" is the authentication scheme, not a password.
    return {"access_token": token(user, mfa), "token_type": "bearer"}  # nosec B105


@app.post("/auth/mfa/setup", dependencies=limited, response_model=MFASetupOut)
def mfa_setup(
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    def run():
        db.refresh(user, with_for_update=True)
        if user.mfa_enabled:
            raise HTTPException(409, "MFA already enabled")
        # Keep an unconfirmed enrollment key stable across setup retries.
        if not user.mfa_secret:
            user.mfa_secret = encrypt(pyotp.random_base32())
        secret = decrypt(user.mfa_secret)
        audit(db, user, "mfa_setup", user.id)
        return {
            "secret": secret,
            "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
                user.email, issuer_name="Amrutam"
            ),
        }

    return write(db, user.id, key, "mfa-setup", {}, run, secret=True)


@app.post("/auth/mfa/confirm", dependencies=limited, response_model=EnabledOut)
def mfa_confirm(
    body: MFAConfirm,
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    def run():
        # Lock account to prevent concurrent use of the same TOTP.
        db.refresh(user, with_for_update=True)
        verify_otp(user, body.otp)
        user.mfa_enabled = 1
        audit(db, user, "mfa_enabled", user.id)
        return {"enabled": True}

    return write(db, user.id, key, "mfa-confirm", body.model_dump(), run)


@app.get("/me", dependencies=limited, response_model=MeOut)
def me(user=Depends(current_user), db=Depends(get_db)):
    profile = db.get(Profile, user.id)
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "name": profile.name if profile else "",
        "mfa_enabled": bool(user.mfa_enabled),
    }


@app.post(
    "/admin/doctors", dependencies=limited, status_code=201, response_model=DoctorRefOut
)
def create_doctor(
    body: DoctorCreate,
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    role(user, "admin")

    def run():
        target = db.get(User, body.user_id, with_for_update=True)
        if not target:
            raise HTTPException(404, "User not found")
        if not target.mfa_enabled:
            raise HTTPException(409, "User must enable MFA first")
        if target.role != "patient":
            raise HTTPException(409, "User must be a patient before promotion")
        target.role = "doctor"
        db.add(Doctor(**body.model_dump()))
        audit(db, user, "doctor_created", target.id)
        return {"doctor_id": target.id}

    return write(db, user.id, key, "create-doctor", body.model_dump(), run)


@app.get("/doctors", dependencies=limited, response_model=list[DoctorOut])
def doctors(
    specialty: str | None = Query(None, max_length=100),
    max_fee_paise: int | None = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    q = (
        select(Doctor, Profile.name)
        .join(Profile, Profile.user_id == Doctor.user_id)
        .where(Profile.name != "Synthetic doctor")
    )

    if specialty:
        q = q.where(Doctor.specialty.ilike(specialty))

    if max_fee_paise is not None:
        q = q.where(Doctor.fee_paise <= max_fee_paise)

    return [
        {
            "id": doctor.user_id,
            "name": name,
            "specialty": doctor.specialty,
            "fee_paise": doctor.fee_paise,
        }
        for doctor, name in db.execute(
            q.order_by(Profile.name, Doctor.user_id)
            .limit(limit)
            .offset(offset)
        )
    ]

@app.post(
    "/doctors/me/slots", dependencies=limited, status_code=201, response_model=IdOut
)
def create_slot(
    body: SlotCreate,
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    role(user, "doctor")

    def run():
        if (
            body.starts_at <= datetime.now(timezone.utc)
            or body.ends_at <= body.starts_at
        ):
            raise HTTPException(422, "Slot must be future and end after start")
        lock(db, "doctor-slots:" + user.id)
        if db.scalar(
            select(Slot.id).where(
                Slot.doctor_id == user.id,
                Slot.starts_at < body.ends_at,
                Slot.ends_at > body.starts_at,
            )
        ):
            raise HTTPException(409, "Overlapping availability")
        slot = Slot(doctor_id=user.id, **body.model_dump())
        db.add(slot)
        db.flush()
        audit(db, user, "slot_created", slot.id)
        return {"id": slot.id}

    return write(db, user.id, key, "slot", body.model_dump(), run)


@app.get(
    "/doctors/{doctor_id}/slots", dependencies=limited, response_model=list[SlotOut]
)
def slots(
    doctor_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    occupied = select(Consultation.slot_id).where(Consultation.status != "cancelled")
    rows = db.scalars(
        select(Slot)
        .where(
            Slot.doctor_id == doctor_id,
            Slot.starts_at > datetime.now(timezone.utc),
            Slot.id.not_in(occupied),
        )
        .order_by(Slot.starts_at)
        .limit(limit)
        .offset(offset)
    )
    return [{"id": s.id, "starts_at": s.starts_at, "ends_at": s.ends_at} for s in rows]


@app.post(
    "/consultations", dependencies=limited, status_code=201, response_model=BookingOut
)
def book(
    body: Booking,
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    role(user, "patient")

    def run():
        slot = db.get(Slot, body.slot_id, with_for_update=True)
        if not slot:
            raise HTTPException(404, "Slot not found")
        start = (
            slot.starts_at.replace(tzinfo=timezone.utc)
            if slot.starts_at.tzinfo is None
            else slot.starts_at
        )
        if start <= datetime.now(timezone.utc):
            raise HTTPException(409, "Slot is in the past")
        if db.scalar(
            select(Consultation.id).where(
                Consultation.slot_id == slot.id, Consultation.status != "cancelled"
            )
        ):
            raise HTTPException(409, "Slot already booked")
        c = Consultation(patient_id=user.id, doctor_id=slot.doctor_id, slot_id=slot.id)
        db.add(c)
        db.flush()
        db.add(
            Payment(
                consultation_id=c.id,
                amount_paise=db.get(Doctor, slot.doctor_id).fee_paise,
            )
        )
        db.add(Outbox(kind="booking_notification", resource_id=c.id))
        audit(db, user, "booked", c.id)
        return {"id": c.id, "status": "booked"}

    return write(db, user.id, key, "book", body.model_dump(), run)


def access(c, user):
    if not c:
        raise HTTPException(404, "Consultation not found")
    if user.id not in (c.patient_id, c.doctor_id):
        raise HTTPException(
            403, "Only consultation participants may access clinical records"
        )


def view(c):
    return {
        "id": c.id,
        "patient_id": c.patient_id,
        "doctor_id": c.doctor_id,
        "slot_id": c.slot_id,
        "status": c.status,
    }


@app.get("/consultations", dependencies=limited, response_model=list[ConsultationOut])
def consultations(
    user=Depends(current_user),
    db=Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    from sqlalchemy.orm import aliased

    patient_profile = aliased(Profile)

    query = (
        select(
            Consultation,
            Slot.starts_at,
            Slot.ends_at,
            Profile.name,
            patient_profile.name,
        )
        .join(Slot, Slot.id == Consultation.slot_id)
        .join(Profile, Profile.user_id == Consultation.doctor_id)
        .outerjoin(patient_profile, patient_profile.user_id == Consultation.patient_id)
        .where(
            (Consultation.patient_id == user.id) | (Consultation.doctor_id == user.id)
        )
        .order_by(Consultation.created_at.desc(), Consultation.id)
        .limit(limit)
        .offset(offset)
    )

    return [
        {
            **view(c),
            "starts_at": start,
            "ends_at": end,
            "doctor_name": doctor_name,
            "patient_name": patient_name,
        }
        for c, start, end, doctor_name, patient_name in db.execute(query)
    ]

@app.get("/consultations/{cid}", dependencies=limited, response_model=ConsultationOut)
def consultation(cid: str, user=Depends(current_user), db=Depends(get_db)):
    c = db.get(Consultation, cid)
    access(c, user)
    return view(c)


@app.patch("/consultations/{cid}", dependencies=limited, response_model=ConsultationOut)
def transition(
    cid: str,
    body: Transition,
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    def run():
        c = db.get(Consultation, cid, with_for_update=True)
        access(c, user)
        allowed = {"booked": {"in_progress", "cancelled"}, "in_progress": {"completed"}}
        if body.status not in allowed.get(c.status, set()):
            raise HTTPException(409, "Invalid state transition")
        if body.status != "cancelled" and user.id != c.doctor_id:
            raise HTTPException(403, "Only assigned doctor may progress consultation")
        if body.status == "completed" and not db.get(Prescription, c.id):
            raise HTTPException(409, "Prescription required before completion")
        c.status = body.status
        if body.status == "cancelled":
            payment = db.scalar(select(Payment).where(Payment.consultation_id == c.id))
            payment.status = "cancelled"
        db.add(Outbox(kind="consultation_" + body.status, resource_id=c.id))
        audit(db, user, "consultation_" + body.status, c.id)
        return view(c)

    return write(db, user.id, key, "transition:" + cid, body.model_dump(), run)


@app.post(
    "/consultations/{cid}/prescription",
    dependencies=limited,
    status_code=201,
    response_model=PrescriptionRefOut,
)
def prescribe(
    cid: str,
    body: PrescriptionCreate,
    user=Depends(current_user),
    db=Depends(get_db),
    key: str | None = Header(None, alias="Idempotency-Key"),
):
    role(user, "doctor")

    def run():
        c = db.get(Consultation, cid, with_for_update=True)
        access(c, user)
        if c.doctor_id != user.id:
            raise HTTPException(403, "Only assigned doctor may prescribe")
        if c.status != "in_progress":
            raise HTTPException(409, "Consultation must be in progress")
        db.add(Prescription(consultation_id=cid, encrypted_text=encrypt(body.text)))
        audit(db, user, "prescription_created", cid)
        return {"consultation_id": cid}

    return write(db, user.id, key, "prescribe:" + cid, body.model_dump(), run)


@app.get(
    "/consultations/{cid}/prescription",
    dependencies=limited,
    response_model=PrescriptionOut,
)
def prescription(cid: str, user=Depends(current_user), db=Depends(get_db)):
    access(db.get(Consultation, cid), user)
    row = db.get(Prescription, cid)
    if not row:
        raise HTTPException(404, "Prescription not found")
    audit(db, user, "prescription_read", cid)
    db.commit()
    return {"consultation_id": cid, "text": decrypt(row.encrypted_text)}


@app.get("/admin/analytics", dependencies=limited, response_model=AnalyticsOut)
def analytics(user=Depends(current_user), db=Depends(get_db)):
    role(user, "admin")
    return {
        "consultations_by_status": dict(
            db.execute(
                select(Consultation.status, func.count()).group_by(Consultation.status)
            ).all()
        ),
        "patients": db.scalar(
            select(func.count()).select_from(User).where(User.role == "patient")
        ),
        "doctors": db.scalar(select(func.count()).select_from(Doctor)),
    }


@app.get("/admin/audit", dependencies=limited, response_model=list[AuditOut])
def audits(
    user=Depends(current_user),
    db=Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    role(user, "admin")
    return [
        {
            "id": a.id,
            "actor_id": a.actor_id,
            "action": a.action,
            "resource_id": a.resource_id,
            "created_at": a.created_at,
        }
        for a in db.scalars(
            select(Audit)
            .order_by(Audit.created_at.desc(), Audit.id)
            .limit(limit)
            .offset(offset)
        )
    ]
