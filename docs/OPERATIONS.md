# Operations and deployment

## Local infrastructure and delivery

Compose is executable infrastructure-as-code for local evaluation. CI runs PostgreSQL
functional/concurrency tests, Bandit, dependency audit and Docker build. It deliberately
does not publish images or deploy to an external account without credentials.
`infra/kubernetes.yaml` is a production-oriented template, not an applied cluster.
Replace image/secret values and configure managed PostgreSQL, ingress TLS and network policies.
It deploys only API and worker; use managed monitoring/backups and a schema migration Job.

No production availability, scale or latency measurements are claimed.

## Health, logs, traces, alerts

`/health/live` is process health; `/health/ready` checks database connectivity. Kubernetes
routes only to ready replicas. `/metrics` exports counters and histogram buckets using
route templates instead of IDs, avoiding unbounded cardinality and patient identifiers.
The endpoint must stay private in production. Logs are JSON objects with correlation ID,
route, status and duration; no request bodies or auth headers. API adds X-Request-ID.
OTLP is enabled by endpoint env var and exports to Jaeger in Compose. No provider endpoint
means instrumentation is disabled. OTLP uses HTTP internally; secure it in production.

PromQL examples:
```
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{method="GET"}[5m])))
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{method=~"POST|PATCH"}[5m])))
sum(rate(http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total[5m])), 0.001)
```

Alert rules are installed in Prometheus for down service, >1% 5xx and slow reads.
Alertmanager and actual email/pager routing are not configured. Add them for operations.
The API latency histogram measures server-side handling, including authentication/DB work.
Add business metrics for outbox age, dead-letter count, DB lock waits, pool saturation and
booking conflicts before production. Synthetic probes should exercise booking and auth,
not just /health/live. Audit and observability are different systems.

## Rate limiting and resource management

The shared PostgreSQL bucket serializes counts per direct-client IP and minute across API
replicas. Limits are 10 auth requests/minute and 120 other domain requests/minute. It uses
request.client.host and ignores arbitrary X-Forwarded-For. The Compose API disables proxy
headers. At a trusted ingress, explicitly configure allowed proxy addresses and edge IP
rate limiting. Leaving a single proxy IP as the client would group all users together.
Replace the DB limiter with Redis/edge controls at high traffic; do not blindly trust headers.
Health/metrics/OpenAPI are outside the domain limiter and must be ingress-restricted.
Expired buckets are removed by the worker. Idempotency records remain durable indefinitely
in this demo; implement an agreed retention policy with safe client retry guarantees.

## Backup and disaster recovery

Target proposal: RPO <=5 minutes, RTO <=60 minutes; neither is measured here.
Production: managed PostgreSQL across availability zones, encrypted nightly full backups,
continuous WAL archive/PITR, separate-region immutable backup copies, monitored archive lag,
30-day baseline retention subject to legal review. Encryption keys are backed up separately
with restricted recovery access. Do not store backup decryption keys next to backups.

Local backup (SQL contains sensitive data; protect the output):
```
docker compose exec -T db pg_dump -U amrutam -d amrutam -Fc > amrutam.dump
```
Use Bash or PowerShell 7.4+ for binary stdout redirection. On older Windows PowerShell,
write the dump inside the db container and use docker compose cp to copy the binary file.
A Docker named volume is persistence, not a backup.

Restore into a separate clean database:
1. Provision database and restore encryption keys from the secret manager.
2. Restore full backup and replay WAL to chosen recovery point.
3. Check schema, row counts, active-slot uniqueness, audit continuity and decrypt samples.
4. Run health, authorization and synthetic consultation tests.
5. Route traffic to restored primary; resume workers after checking pending jobs.
6. Record elapsed time/data loss and compare with RTO/RPO. Test quarterly.

Local pg_restore example after creating a disposable recovery database:
```
docker compose exec -T db pg_restore -U amrutam -d recovery --no-owner < amrutam.dump
```
Never restore over a running production database for a drill.

## Retry, dead-letter and incident handling

Worker retries have exponential backoff + random jitter, cap 3600s, dead after 8 failed
attempts. SKIP LOCKED allows worker replicas to claim different rows. The synchronous
delivery adapter is invoked while holding its row lock; impose provider timeouts when
replacing the demo adapter. A provider may receive a delivery twice on crash; stable delivery
IDs must be deduplicated externally. The demo logs an event, not a delivered email.

For dead rows, inspect provider status by outbox delivery ID, resolve the cause, then reset
status to pending/available_at in an audited operator procedure. Never mark financial
operations successful from a notification status. Payment records are local placeholders.
On DB outage: readiness becomes 503, domain operations return safe errors, clients retry
transient failures with bounded backoff. No local fallback writes are accepted.

## Load and SLO evaluation

The load script targets a running deployment and reads public doctor search. It reports
observed count/errors/p95; it does not prove a 24-hour 100k consultation workload.
```
python scripts/load_reads.py --url http://localhost:8000 --requests 60 --concurrency 4
```
The built-in 120/min direct-IP limit is intentional; stay under it or test behind a configured
production ingress. For a serious benchmark, provision dedicated synthetic accounts/slots,
measure a realistic mix at ~23 peak bookings/sec plus reads, include conflict/retry traffic,
run soak/failover tests, record DB resources and p95 by endpoint. Never disable authorization
or booking integrity to improve a benchmark. Track error-budget burn, not only average latency.

## Deployment/rollback

Build immutable images after CI passes; scan and pin digests, apply additive schema migrations
as a separate job, then roll out API/worker with readiness checks and a restricted service
account. Use at least two API replicas and a pod disruption budget. Keep DB connection limits
bounded per replica (SQLAlchemy default pool: 5 + 10 overflow; tune to actual DB capacity).
Roll back application images only while schema is backward compatible. init-db is the initial
bootstrap, not a versioned migration framework. Integrate Alembic before schema evolution.
