import uuid
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest, pyotp
from sqlalchemy import select, func
from app.db import SessionLocal, engine
from app.models import Consultation, Outbox, Payment, Prescription, User
from app.security import decrypt, token


def headers(actors, name, key=None):
    return {
        "Authorization": actors[name]["Authorization"],
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


def new_slot(client, actors, offset=1):
    start = datetime.now(timezone.utc) + timedelta(days=offset)
    r = client.post(
        "/doctors/me/slots",
        headers=headers(actors, "doctor"),
        json={
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def booking(client, actors):
    sid = new_slot(client, actors)
    r = client.post(
        "/consultations", headers=headers(actors, "patient"), json={"slot_id": sid}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], sid


def test_health_and_schema(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert "/consultations" in client.get("/openapi.json").json()["paths"]
    assert b"http_requests_total" in client.get("/metrics").content


def test_register_login_and_no_role_escalation(client):
    body = {
        "email": "new@example.com",
        "password": "StrongPassword123!",
        "name": "New",
        "role": "admin",
    }
    h = {"Idempotency-Key": "registration-1"}
    r = client.post("/auth/register", json=body, headers=h)
    assert r.status_code == 201 and r.json()["role"] == "patient"
    assert client.post("/auth/register", json=body, headers=h).json() == r.json()
    assert (
        client.post(
            "/auth/login", json={"email": body["email"], "password": "wrong"}
        ).status_code
        == 401
    )
    login = client.post(
        "/auth/login", json={"email": body["email"], "password": body["password"]}
    )
    assert login.status_code == 200
    assert (
        client.get(
            "/me", headers={"Authorization": "Bearer " + login.json()["access_token"]}
        ).json()["role"]
        == "patient"
    )


def test_validation_and_permissions(client, actors):
    assert client.get("/consultations").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert (
        client.get("/admin/analytics", headers=headers(actors, "patient")).status_code
        == 403
    )
    assert (
        client.post(
            "/doctors/me/slots",
            headers=headers(actors, "patient"),
            json={
                "starts_at": "2030-01-01T10:00:00Z",
                "ends_at": "2030-01-01T11:00:00Z",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/auth/register",
            headers={"Idempotency-Key": "valid-key"},
            json={"email": "bad", "password": "x", "name": "n"},
        ).status_code
        == 422
    )
    assert client.get("/doctors?limit=1000").status_code == 422


def test_booking_idempotency_and_conflict(client, actors):
    sid = new_slot(client, actors)
    h = headers(actors, "patient", "booking-unique-1")
    first = client.post("/consultations", headers=h, json={"slot_id": sid})
    assert first.status_code == 201
    assert (
        client.post("/consultations", headers=h, json={"slot_id": sid}).json()
        == first.json()
    )
    assert (
        client.post(
            "/consultations", headers=h, json={"slot_id": "different"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/consultations", headers=headers(actors, "other"), json={"slot_id": sid}
        ).status_code
        == 409
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Consultation)) == 1
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
        assert db.scalar(select(func.count()).select_from(Outbox)) == 1


def test_lifecycle_and_encrypted_prescription(client, actors):
    cid, sid = booking(client, actors)
    assert (
        client.get(
            f"/consultations/{cid}", headers=headers(actors, "other")
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/consultations/{cid}", headers=headers(actors, "admin")
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "patient"),
            json={"status": "in_progress"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "doctor"),
            json={"status": "completed"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "doctor"),
            json={"status": "in_progress"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "doctor"),
            json={"status": "completed"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/consultations/{cid}/prescription",
            headers=headers(actors, "doctor"),
            json={"text": "Clinical test prescription"},
        ).status_code
        == 201
    )
    with SessionLocal() as db:
        row = db.get(Prescription, cid)
        assert "Clinical test prescription" not in row.encrypted_text
        assert decrypt(row.encrypted_text) == "Clinical test prescription"
    assert (
        client.get(
            f"/consultations/{cid}/prescription", headers=headers(actors, "patient")
        ).json()["text"]
        == "Clinical test prescription"
    )
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "doctor"),
            json={"status": "completed"},
        ).json()["status"]
        == "completed"
    )
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "doctor"),
            json={"status": "cancelled"},
        ).status_code
        == 409
    )


def test_cancel_releases_slot(client, actors):
    cid, sid = booking(client, actors)
    assert (
        client.patch(
            f"/consultations/{cid}",
            headers=headers(actors, "patient"),
            json={"status": "cancelled"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/consultations", headers=headers(actors, "other"), json={"slot_id": sid}
        ).status_code
        == 201
    )
    with SessionLocal() as db:
        assert (
            db.scalar(select(Payment).where(Payment.consultation_id == cid)).status
            == "cancelled"
        )


def test_overlapping_slots_and_search(client, actors):
    sid = new_slot(client, actors)
    from app.models import Slot

    with SessionLocal() as db:
        s = db.get(Slot, sid)
        start = s.starts_at.replace(tzinfo=timezone.utc)
        end = s.ends_at.replace(tzinfo=timezone.utc)
    assert (
        client.post(
            "/doctors/me/slots",
            headers=headers(actors, "doctor"),
            json={"starts_at": start.isoformat(), "ends_at": end.isoformat()},
        ).status_code
        == 409
    )
    assert (
        len(client.get("/doctors?specialty=Ayurveda&max_fee_paise=50000").json()) == 1
    )
    assert client.get("/doctors?max_fee_paise=1").json() == []
    assert len(client.get(f"/doctors/{actors['doctor']['id']}/slots").json()) == 1


def test_missing_idempotency(client, actors):
    assert (
        client.post(
            "/consultations",
            headers={"Authorization": actors["patient"]["Authorization"]},
            json={"slot_id": "x"},
        ).status_code
        == 400
    )


def test_mfa_enable_replay_and_enforcement(client, actors):
    h = headers(actors, "patient", "mfa-setup-key")
    setup = client.post("/auth/mfa/setup", headers=h)
    assert setup.status_code == 200
    assert client.post("/auth/mfa/setup", headers=h).json() == setup.json()
    otp = pyotp.TOTP(setup.json()["secret"]).now()
    assert (
        client.post(
            "/auth/mfa/confirm", headers=headers(actors, "patient"), json={"otp": otp}
        ).status_code
        == 200
    )
    assert client.get("/me", headers=headers(actors, "patient")).status_code == 403
    assert (
        client.post(
            "/auth/login",
            json={
                "email": "patient@example.com",
                "password": "StrongPassword123!",
                "otp": otp,
            },
        ).status_code
        == 401
    )
    with SessionLocal() as db:
        user = db.get(User, actors["patient"]["id"])
        assert setup.json()["secret"] not in user.mfa_secret
        user.last_totp = -1
        db.commit()
    r = client.post(
        "/auth/login",
        json={
            "email": "patient@example.com",
            "password": "StrongPassword123!",
            "otp": otp,
        },
    )
    assert r.status_code == 200
    assert (
        client.get(
            "/me", headers={"Authorization": "Bearer " + r.json()["access_token"]}
        ).status_code
        == 200
    )


def test_privileged_token_requires_mfa(client, actors):
    with SessionLocal() as db:
        u = db.get(User, actors["doctor"]["id"])
        t = token(u, mfa=False)
    assert (
        client.get("/me", headers={"Authorization": "Bearer " + t}).status_code == 403
    )


def test_rate_limit(client):
    for i in range(10):
        assert (
            client.post(
                "/auth/login", json={"email": "nobody@example.com", "password": "x"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "x"}
        ).status_code
        == 429
    )


def test_admin_analytics_and_audit(client, actors):
    cid, _ = booking(client, actors)
    assert client.get("/admin/analytics", headers=headers(actors, "admin")).json()[
        "consultations_by_status"
    ] == {"booked": 1}
    assert any(
        a["resource_id"] == cid
        for a in client.get("/admin/audit", headers=headers(actors, "admin")).json()
    )


def test_worker_success_and_retry(client, actors, monkeypatch):
    import app.worker as worker
    from app.models import now

    booking(client, actors)
    monkeypatch.setattr(
        worker, "deliver", lambda *a: (_ for _ in ()).throw(RuntimeError("temporary"))
    )
    assert worker.tick()
    with SessionLocal() as db:
        row = db.scalar(select(Outbox))
        assert row.attempts == 1 and row.status == "pending"
        row.available_at = now() - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(worker, "deliver", lambda *a: None)
    assert worker.tick()
    with SessionLocal() as db:
        assert db.scalar(select(Outbox)).status == "delivered"


@pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="Requires real PostgreSQL row locks"
)
def test_concurrent_bookings(client, actors):
    sid = new_slot(client, actors)

    def request(name):
        return client.post(
            "/consultations", headers=headers(actors, name), json={"slot_id": sid}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, ["patient", "other"]))
    assert sorted(results) == [201, 409]


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Requires real PostgreSQL advisory locks",
)
def test_concurrent_idempotency(client, actors):
    sid = new_slot(client, actors)
    h = headers(actors, "patient", "concurrent-key")

    def request(_):
        return client.post("/consultations", headers=h, json={"slot_id": sid})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, range(2)))
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json() == results[1].json()


def test_duplicate_prescription_is_immutable(client, actors):
    cid, _ = booking(client, actors)
    client.patch(
        f"/consultations/{cid}",
        headers=headers(actors, "doctor"),
        json={"status": "in_progress"},
    )
    h = headers(actors, "doctor", "prescription-key-1")
    r = client.post(
        f"/consultations/{cid}/prescription", headers=h, json={"text": "Original"}
    )
    assert r.status_code == 201
    assert (
        client.post(
            f"/consultations/{cid}/prescription", headers=h, json={"text": "Original"}
        ).json()
        == r.json()
    )
    assert (
        client.post(
            f"/consultations/{cid}/prescription",
            headers=headers(actors, "doctor"),
            json={"text": "Changed"},
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/consultations/{cid}/prescription", headers=headers(actors, "patient")
        ).json()["text"]
        == "Original"
    )


def test_failed_request_does_not_reserve_key(client, actors):
    h = headers(actors, "patient", "recoverable-key")
    assert (
        client.post(
            "/consultations", headers=h, json={"slot_id": "missing"}
        ).status_code
        == 404
    )
    sid = new_slot(client, actors)
    assert (
        client.post("/consultations", headers=h, json={"slot_id": sid}).status_code
        == 201
    )


def test_timezone_validation(client, actors):
    r = client.post(
        "/doctors/me/slots",
        headers=headers(actors, "doctor"),
        json={"starts_at": "2030-01-01T10:00:00", "ends_at": "2030-01-01T11:00:00"},
    )
    assert r.status_code == 422


def test_worker_dead_letter(client, actors, monkeypatch):
    import app.worker as worker

    booking(client, actors)
    with SessionLocal() as db:
        row = db.scalar(select(Outbox))
        row.attempts = 7
        db.commit()
    monkeypatch.setattr(
        worker, "deliver", lambda *a: (_ for _ in ()).throw(RuntimeError("down"))
    )
    assert worker.tick()
    with SessionLocal() as db:
        row = db.scalar(select(Outbox))
        assert row.status == "dead" and row.attempts == 8


@pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="PostgreSQL trigger integration"
)
def test_postgres_audit_immutable(client, actors):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    import subprocess, sys, os

    env = dict(os.environ)
    env["DATABASE_URL"] = str(engine.url.render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "app.manage", "init-db"], env=env, check=True)
    booking(client, actors)
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(text("DELETE FROM audit_logs"))
            db.commit()


def test_frontend_assets_and_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Amrutam" in response.text
    assert "/assets/app.js" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200
    assert client.get("/assets/../config.py").status_code == 404


def test_frontend_profile_and_appointment_context(client, actors):
    cid, sid = booking(client, actors)
    me = client.get("/me", headers=headers(actors, "patient")).json()
    assert me["name"] == "patient" and me["mfa_enabled"] is False
    rows = client.get("/consultations", headers=headers(actors, "patient")).json()
    assert rows[0]["id"] == cid
    assert rows[0]["starts_at"] and rows[0]["ends_at"]
    assert rows[0]["doctor_name"] == "doctor"
    assert client.get("/consultations", headers=headers(actors, "other")).json() == []
