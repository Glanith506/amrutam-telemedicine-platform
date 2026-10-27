"""Trusted local demo: run inside API container; synthetic data only."""

import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pyotp

from app.db import SessionLocal
from app.models import User, Audit


def main():
    suffix = uuid.uuid4().hex[:10]
    credentials = {}
    client = httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=30,
        trust_env=False,
    )
    auth_count = 0
    auth_minute = int(time.time()) // 60

    def call(method, path, who=None, body=None, key=None, expected=200):
        nonlocal auth_count, auth_minute

        if path.startswith("/auth/"):
            minute = int(time.time()) // 60

            if minute != auth_minute:
                auth_count = 0
                auth_minute = minute

            if auth_count >= 10:
                print("Waiting for the next auth rate-limit window...")
                time.sleep(61 - time.time() % 60)
                auth_count = 0
                auth_minute = int(time.time()) // 60

            auth_count += 1

        headers = {"Idempotency-Key": key or str(uuid.uuid4())}

        if who:
            headers["Authorization"] = "Bearer " + credentials[who]["token"]

        response = client.request(
            method,
            path,
            json=body,
            headers=headers,
        )

        if response.status_code != expected:
            raise RuntimeError(
                f"{method} {path}: expected {expected}, "
                f"got {response.status_code}: {response.text}"
            )

        return response.json()

    try:
        for name in ("admin", "doctor", "patient", "other"):
            email = f"demo-{name}-{suffix}@example.com"
            password = uuid.uuid4().hex + "Aa!"

            row = call(
                "POST",
                "/auth/register",
                body={
                    "email": email,
                    "password": password,
                    "name": "Synthetic " + name,
                },
                expected=201,
            )

            login = call(
                "POST",
                "/auth/login",
                body={"email": email, "password": password},
            )

            credentials[name] = {
                "id": row["id"],
                "email": email,
                "password": password,
                "token": login["access_token"],
            }

            print(f"Registered synthetic {name}")

            if name in ("admin", "doctor"):
                setup = call("POST", "/auth/mfa/setup", who=name)
                credentials[name]["mfa"] = setup["secret"]

                call(
                    "POST",
                    "/auth/mfa/confirm",
                    who=name,
                    body={"otp": pyotp.TOTP(setup["secret"]).now()},
                )

        # Trusted operator action: bootstrap the demo admin locally.
        with SessionLocal() as db:
            user = db.get(User, credentials["admin"]["id"])
            user.role = "admin"

            db.add(
                Audit(
                    actor_id="operator-demo",
                    action="promoted_admin",
                    resource_id=user.id,
                )
            )
            db.commit()

        print("MFA configured and synthetic admin bootstrapped.")

        for name in ("admin", "doctor"):
            account = credentials[name]

            login = call(
                "POST",
                "/auth/login",
                body={
                    "email": account["email"],
                    "password": account["password"],
                    "otp": pyotp.TOTP(account["mfa"]).now(),
                },
            )

            account["token"] = login["access_token"]

        call(
            "POST",
            "/admin/doctors",
            who="admin",
            body={
                "user_id": credentials["doctor"]["id"],
                "specialty": "Ayurveda",
                "fee_paise": 50000,
            },
            expected=201,
        )

        # Roles are read from the database on each authenticated request.
        start = datetime.now(timezone.utc) + timedelta(days=1)

        slot = call(
            "POST",
            "/doctors/me/slots",
            who="doctor",
            body={
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
            },
            expected=201,
        )

        key = str(uuid.uuid4())
        payload = {"slot_id": slot["id"]}

        booking = call(
            "POST",
            "/consultations",
            who="patient",
            body=payload,
            key=key,
            expected=201,
        )

        replay = call(
            "POST",
            "/consultations",
            who="patient",
            body=payload,
            key=key,
            expected=201,
        )

        if replay != booking:
            raise RuntimeError(
                "Idempotency replay returned a different result"
            )

        call(
            "POST",
            "/consultations",
            who="other",
            body=payload,
            expected=409,
        )

        print(
            "Booking created; same-key retry replayed; "
            "competing booking rejected (409)"
        )

        consultation_id = booking["id"]

        call(
            "GET",
            f"/consultations/{consultation_id}",
            who="other",
            expected=403,
        )

        call(
            "PATCH",
            f"/consultations/{consultation_id}",
            who="doctor",
            body={"status": "in_progress"},
        )

        call(
            "POST",
            f"/consultations/{consultation_id}/prescription",
            who="doctor",
            body={
                "text": "Synthetic demonstration only; not medical advice."
            },
            expected=201,
        )

        call(
            "PATCH",
            f"/consultations/{consultation_id}",
            who="doctor",
            body={"status": "completed"},
        )

        call(
            "GET",
            f"/consultations/{consultation_id}/prescription",
            who="patient",
        )

        print(
            "Unauthorized account denied; prescription created "
            "and patient access verified"
        )
        print("Consultation completed:", consultation_id)
        print(
            "Admin analytics:",
            call("GET", "/admin/analytics", who="admin"),
        )
        print("DEMO PASSED. Review Prometheus, Jaeger and worker logs.")

    finally:
        client.close()


if __name__ == "__main__":
    main()