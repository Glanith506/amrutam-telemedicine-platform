# Verification report

Updated: 27 October 2026

The project was checked locally on Windows using Docker Desktop,
PostgreSQL 16 and Node.js 24.12.0. The API container uses Python 3.12.
The local security scans ran with Python 3.11.9.

## Test results

| Check | Result |
|---|---|
| Frontend DOM tests | 10 passed, 0 failed |
| Backend tests against PostgreSQL | 22 passed, 0 skipped |
| Concurrent bookings for the same slot | Passed |
| Concurrent requests using the same idempotency key | Passed |
| PostgreSQL audit log protection | Passed |
| Docker image build and Compose startup | Passed |
| End-to-end API demo against PostgreSQL | Passed |
| Prometheus metrics collection | Target showed UP |
| Jaeger tracing | API traces visible |
| Structured API logs | Request IDs, routes, status codes and durations visible |
| Background worker | Booking and consultation events appeared in worker logs |
| Bandit scan | 0 reported findings after two reviewed suppressions |
| Dependency scan | pip-audit reported no known vulnerabilities |

These results were collected through local commands, terminal output
and checks in the browser. They do not represent a production load test.

## Backend testing

The backend suite ran inside a temporary Docker container against a
separate database named `amrutam_test`. The normal application database
was not used for these tests.

The result was:

    22 passed, 1 warning in 18.83s

The tests cover authentication, role restrictions, MFA, availability,
booking, consultation status changes, prescriptions, analytics, audit
logs and worker behavior.

The PostgreSQL-specific tests also passed. These check competing bookings,
concurrent idempotency replay and protection against changes to audit rows.

The warning came from Starlette's test client using a deprecated httpx
integration. It did not cause a test failure.

The test suite drops and recreates tables. It must only run against a
disposable test database.

## Frontend testing

The frontend test result was:

    10 passed, 0 failed

The tests use jsdom and synthetic API responses. They check:

- Doctor listings and conversion of fees from rupees to paise.
- Patient booking requests with authentication and idempotency headers.
- Registration and clearing the password field afterwards.
- Display of failed login messages.
- Doctor availability requests using UTC timestamps.
- Admin analytics and doctor approval requests.
- Safe display of untrusted doctor names.
- Visitor navigation without private account pages.
- Registration from the public homepage.
- Search filters carried from the homepage to the doctor directory.

The visitor homepage and role-based screens were also checked manually
in Chrome during development. A full browser automation suite and
cross-browser accessibility review have not been completed.

Frontend files are in `frontend/`. Backend files are in `backend/`.
FastAPI serves both through the same local address.

## End-to-end demo

The following command completed successfully:

    docker compose exec api python -m app.demo

The demo registered sample accounts, configured MFA and set up a sample
admin and doctor. It then checked that:

- A patient could book an available slot.
- Retrying with the same idempotency key returned the original booking.
- Another patient could not book the occupied slot and received HTTP 409.
- An unrelated account could not access the consultation.
- The assigned doctor could start the consultation and issue a prescription.
- The patient could read their prescription.
- The doctor could complete the consultation.
- Admin analytics reflected the stored consultations.

The final output included:

    DEMO PASSED. Review Prometheus, Jaeger and worker logs.

Each run creates additional sample accounts and records. Increasing
patient, doctor and consultation counts after repeated runs is expected.

## Observability

Prometheus was checked at `http://localhost:9090/targets`.
The `amrutam` target showed UP and was scraping `api:8000/metrics`.

Jaeger was checked at `http://localhost:16686/`.
Traces were visible for the `amrutam-api` service, including consultation,
prescription and analytics requests.

API logs contained structured entries with request IDs, methods, routes,
status codes and request durations.

Worker logs showed events for booking, consultation start and consultation
completion. The notification adapter currently logs these events; it does
not send emails or messages to an external provider.

These checks confirm local metrics, logs and trace collection. They do
not establish production availability or latency guarantees.

## Security scans

Bandit was run against `backend/app`.

One finding in the demo was addressed by replacing an `assert` with an
explicit exception, so the check still runs when Python optimization
is enabled.

Two low-severity findings were reviewed and suppressed at the relevant lines:

- B105: `"bearer"` identifies the authentication scheme. It is not a password.
- B311: `random.uniform()` supplies retry jitter. It is not used to generate
  credentials, tokens or encryption keys.

The final scan reported zero findings. Bandit also printed a warning about
a B105 suppression on a node without a matching finding. This was a scanner
warning, not a reported vulnerability.

The dependency scan was run with:

    python -m pip_audit -r backend/requirements.lock.txt

It reported:

    No known vulnerabilities found

Scanner results describe the checks performed at that time. They are not
a guarantee that the application has no security weaknesses.

Files already present in `docs/evidence/` contain earlier scan results.
They should not be treated as output from these latest local runs.

## Documentation and CI

The project includes an OpenAPI schema, a four-page architecture PDF,
architecture diagrams, a security checklist, a threat model and an
operations guide.

The GitHub Actions workflow is configured to run frontend tests,
PostgreSQL backend tests, Bandit, dependency scanning and a Docker build.

A successful remote GitHub Actions run has not yet been confirmed.
The local results above should not be described as a completed CI run.

## Remaining limits

The following items remain unverified or outside the current implementation:

- Capacity for 100,000 consultations per day.
- p95 read latency below 200 ms and write latency below 500 ms under
  a representative workload.
- 99.95% production availability.
- Kubernetes deployment, production TLS and database failover.
- Backup restoration and measured recovery time or data loss.
- Multi-replica production behavior under load.
- External notification delivery and payment processing.
- Automated production release and deployment.

Caching, partitioning, disaster recovery and a payment saga are discussed
in the design documents. They should not be presented as deployed features.

Payments currently use pending/cancelled ledger records; no money is
collected. Doctor credentials are assumed to be checked outside the
application before an admin grants doctor access.

The five-minute submission video still needs to be recorded and linked
from the README.