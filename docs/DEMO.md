# Five-minute video guide

Record your own screen with the running project. Use synthetic accounts. Do not show .env,
access tokens, MFA seeds/QR codes or actual patient information. The automatic demo hides
these values. Explain the boundaries honestly; this file is a script, not a recorded video.

**0:00–0:40 — Goal and structure**
“This is a backend for doctor consultations. It supports patients, doctors and admins.
I used FastAPI and PostgreSQL, with separate modules for authentication, data models,
transaction helpers and background jobs.” Show folder tree and architecture diagram.

**0:40–1:20 — Running services**
Show `docker compose ps`, Swagger at /docs, and readiness endpoint. Explain database,
API, worker, Prometheus and Jaeger. Avoid opening secrets.

**1:20–2:50 — Core demo**
Run `docker compose exec api python -m app.demo`. While it waits for the next authentication rate-limit window,
explain that a doctor/admin must log in with password plus authenticator code.
The output shows synthetic account registration, MFA, doctor provisioning, future slot,
booking, retry replay and a competing booking rejected with 409.

**2:50–3:30 — Clinical ownership**
Show demo progression to in_progress, prescription issuance, completion and patient read.
Explain that only the assigned doctor writes a prescription and only the patient/doctor
can read it. Prescription content is encrypted in the database. Admin gets aggregate counts.

**3:30–4:15 — Reliability and tests**
Show tests and CI. Explain slot row locks and the partial unique index. A repeated
idempotency key returns the original result; the outbox row is committed with booking.
Be accurate about which tests you ran locally versus CI.

**4:15–4:45 — Observability**
Open Prometheus and graph `http_requests_total`. Show Jaeger traces for amrutam-api.
Show an API log containing correlation ID and route without any patient text.

**4:45–5:00 — Limits and next steps**
“Docker runs this locally. Production needs TLS, managed secrets, HA database and a
real notification/payment provider. Scale and uptime are design targets; I have not
claimed they are proven.”

Possible follow-up questions: Why row locks AND a unique index? What if the API crashes
after committing? Can an admin read prescriptions? What if a worker sends twice? Why is
SQLite insufficient for concurrency testing? How would a payment saga compensate failure?

## Optional frontend demonstration

Open http://localhost:8000/ after installing the frontend update. Sign in to your own
synthetic patient account and show the doctor directory, filters and available times.
Use a doctor account to publish a future slot, then book it as a patient. Show doctor
consultation start/prescription/completion, and read it as the patient. Do not show MFA
setup keys, credentials or real clinical information in the recording. The account
provisioning steps are in FRONTEND_SETUP.md.
