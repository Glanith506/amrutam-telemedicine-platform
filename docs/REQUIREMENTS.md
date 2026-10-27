# Assignment coverage and boundaries

| Requirement | Delivered evidence | Boundary |
|---|---|---|
| Python / PostgreSQL / REST | app/, requirements.txt, compose.yaml | SQLite used only for portable tests |
| Auth + roles | /auth, /me, admin doctor provisioning, CLI admin bootstrap | Email verification/password recovery not built |
| MFA / RBAC | TOTP enroll/confirm, privileged MFA enforcement, role and ownership checks | No automated MFA recovery |
| Doctor availability / booking | Slot create/list, overlap detection, locked booking | No recurring scheduling or patient-overlap policy |
| Consultation / prescriptions | State machine, encrypted prescription, participant-only access | No video/media or medical validity checking |
| Search / filtering | Specialty, fee, paginated doctor directory, available slots | No full text index/search service |
| Compliance / audit trails | Transactional audit and PG append-only trigger, security doc | No compliance certification or full consent/retention product |
| Admin analytics | Status counts and patient/doctor totals | No reporting warehouse |
| Required core tables | users, profiles, doctors, availability_slots, consultations, prescriptions, payments, audit_logs | Payments pending/cancelled only; no gateway |
| Dependency injection / modular services | get_db/current_user dependencies, security/services/db/models modules | Single deployable API |
| Idempotent writes | Fingerprinted transactional replay for domain mutations | Login consumes OTP; operator tools are trusted local actions |
| Async jobs | Durable outbox + independent worker, retries/dead state | Notification adapter logs synthetic events; no actual email |
| Rate limits / validation / secrets | Shared DB limiter, Pydantic constraints, generated env | Production edge policy/secret manager required |
| OpenAPI | openapi.json, /docs and /openapi.json | Generated from actual routes |
| Architecture docs / diagrams | ARCHITECTURE.md | Includes explicitly marked future designs |
| Retry/backoff / transactions / saga | services.py, worker.py, architecture doc | Real gateway saga is proposed, not implemented |
| Caching / partitioning | Architecture decisions and invalidation/uniqueness plans | Redis and partitioning intentionally not activated |
| Backup / disaster recovery | OPERATIONS.md, restore drill and RTO/RPO proposals | No real restore drill/HA benchmark performed |
| Containers / IaC | Dockerfile, Compose, Kubernetes template | K8s template not deployed |
| Tests / CI | tests/, GitHub workflow | See executed test report |
| Metrics / logs / traces | Prometheus, structured request logs, OTLP + Jaeger | Paging destination not configured |
| OWASP / threat model / encryption / rotation | SECURITY.md, field encryption, rotation settings | TLS, KMS, disk encryption are production setup tasks |
| 100k/day / p95 objectives / 99.95% | Capacity assumptions, probes and load script, deployment plan | Targets are NOT measured guarantees |
| 5-minute demo | Runnable app.demo and DEMO.md | User records actual video; no video supplied |

No real external accounts, credentials or patient data are included. Read the source and run
the demo before submitting so you can explain the transaction and security choices.

## Frontend addition

`app/static` provides the browser portal on `/`; it uses the existing API and adds no public
role-escalation endpoint. `FRONTEND_SETUP.md` explains preserving current data and onboarding
admin/doctor accounts. Node is only an optional DOM-test dependency.
