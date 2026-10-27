# Amrutam Telemedicine Consultation Platform
A telemedicine consultation platform with patient, doctor and admin
accounts. Patients can find doctors and book consultations. Doctors can
publish availability, manage consultations and issue prescriptions.
Admins can grant doctor access and view analytics and audit records.

The backend uses Python, FastAPI, PostgreSQL and SQLAlchemy. The frontend
uses HTML, CSS and JavaScript. Docker Compose runs the application and
its supporting services.

Frontend code is in **frontend/**. Python backend code is in **backend/**.
FastAPI serves the frontend and API together at http://localhost:8000/.
This is a separation of source folders; a second server is not needed.

 ## Demo Video

[Watch the project demo][(https://drive.google.com/file/d/1zlBcB1Cei6qauURfe5nTGKflwqsQAiFj/view?usp=drive_link)]

## Updating an existing installation

If you have an older version of this project, follow the steps in
[UPDATE_EXISTING_PROJECT.md](UPDATE_EXISTING_PROJECT.md).

Keep your existing `.env` file and database volume.

## Folder map

- frontend/index.html — browser interface
- frontend/styles.css — responsive styling
- frontend/app.js — API client and screens
- frontend/tests/ — optional DOM integration tests
- backend/app/ — FastAPI, models, schemas, security, workers and operator CLI
- backend/tests/ — backend tests
- backend/requirements.lock.txt — pinned Python packages
- backend/openapi.json — API contract
- backend/Dockerfile — build recipe (context is project root)
- compose.yaml — local infrastructure and services
- scripts/ — initial secret generation
- docs/ — architecture PDF/diagrams, security, operations and verification

## Fresh installation

Requires Python 3.12+ and Docker Desktop with its engine running.
In the folder containing compose.yaml:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install cryptography
.venv\Scripts\python scripts/generate_env.py
docker compose up --build -d
```

On macOS/Linux use .venv/bin/python instead.

Frontend: http://localhost:8000/
Swagger: http://localhost:8000/docs
Prometheus: http://localhost:9090
Jaeger: http://localhost:16686

Automatic synthetic demo: `docker compose exec api python -m app.demo`.
Patient/doctor/admin setup is in **docs/FRONTEND_GUIDE.md**. Demo credentials are not
printed or saved; register your own synthetic accounts for UI use.

## Tests and local development

From backend/: install requirements.lock.txt into a virtual environment, then run
`python -m pytest -q`. Tests default to isolated SQLite. PostgreSQL-specific checks
run in CI with TEST_DATABASE_URL pointing at a disposable database only: tests drop tables.
The backend reads .env from the project root; environment variables override its values.
For local Python serving, configure DATABASE_URL for PostgreSQL and from backend/ run
`python -m uvicorn app.main:app --reload`.

From frontend/: optional Node 24+ DOM tests use `npm ci --ignore-scripts` and
`npm run test:ui`. Node is not needed for normal Docker startup. Do not open index.html
as a local file: the frontend needs its same-origin API.
## Verification

The following checks passed locally:

- 10 frontend DOM tests.
- 22 backend tests against a separate PostgreSQL test database.
- End-to-end demo using sample accounts.
- Prometheus metrics collection and Jaeger traces.
- Bandit scan with two reviewed suppressions.
- pip-audit reported no known vulnerabilities in the locked dependencies.

See [docs/VERIFICATION.md](docs/VERIFICATION.md) for details and limits.

## Scope

Auth/MFA, role/participant access, doctor search/availability, booking/idempotency,
consultations, encrypted prescriptions, analytics/audit, outbox, monitoring and CI.
Notifications use a demo logger and payments use a pending/cancelled ledger.
Production hosting, TLS/HA and scale/SLO measurements remain release tasks.
The interface was checked manually in Chrome. Automated visual and
cross-browser testing have not been completed.

