# Security checklist and threat model

## Trust boundaries and data classification

Untrusted clients cross TLS/WAF into the API; JWT authenticates the account. API and worker
cross a private-network boundary to PostgreSQL. The worker adapter crosses a provider
boundary when real notifications are integrated. Prometheus/Jaeger are operator-only.
The database, CI secrets, encryption keys and operator shell are high-trust assets.

| Data | Classification | Protection |
|---|---|---|
| Passwords | Credentials | Argon2 hash, never returned |
| TOTP secrets | Credentials | Fernet field encryption, one-time enrollment display |
| JWT/encryption keys | Secrets | Env locally; secret manager/KMS in production |
| Prescription text | Sensitive clinical | Fernet authenticated encryption; participant access |
| Email/name | Personal | Role/ownership controls; production disk encryption + TLS |
| Booking metadata | Sensitive personal | Ownership controls, no-store responses |
| Audit | Sensitive operational | Metadata only; append-only trigger; restricted read |
| Metrics/logs/traces | Operational | No body/email/token logging; private access |

## Attack analysis

| Threat / surface | Implemented mitigation | Residual risk / production action |
|---|---|---|
| Broken object-level access | Participant checks on each clinical endpoint | Add independent authorization review and tenant tests if multitenant |
| Privilege escalation | Public register always patient; doctor promotion admin-only; initial admin operator CLI | Protect operator IAM and database credentials |
| Credential stuffing | Argon2, shared DB auth rate buckets, generic login error | Edge account/device protection, breached-password checks |
| Stolen password | TOTP required for privileged roles; optional for patient | Patient MFA can be mandated; recovery flow not implemented |
| TOTP replay | Account row lock and monotonic accepted time step | Time synchronization and secure enrollment device |
| JWT tampering | Fixed HS256 algorithm, expiry, issuer/audience/subject verification | 30-minute expiry; no refresh/revocation endpoint; use IdP or token-version revocation |
| Duplicate booking/request retries | Slot lock, partial unique index, transaction-key lock, durable response | PostgreSQL concurrency tests in CI; don't use SQLite in deployment |
| SQL injection | ORM bound parameters; fixed SQL only | Scan/review all future queries |
| Mass assignment | Explicit input models; role omitted from registration schema | Unknown fields ignored; never map arbitrary JSON into ORM |
| Excessive inputs / DoS | Field limits, pagination caps, rate limiting | Add ingress body/connection limits and timeouts |
| XSS/CSRF | JSON API, Bearer header, no cookie auth, no permissive CORS | UI escapes dynamic text; CSRF if cookie auth is added |
| SSRF | No user-supplied outbound URL fetches | Restrict egress when adding integrations |
| Secret/data disclosure | No committed .env; encrypted prescriptions/MFA; no payload logging | KMS, disk/backups encryption; audit access to keys |
| Audit tampering | PG trigger blocks row UPDATE/DELETE | Database owner can disable trigger; use non-owner role + external WORM archive |
| Supply chain | Pinned direct dependencies, Bandit + pip-audit CI | Resolve findings before release; pin container digests, transitive lockfile and SBOM |
| Payment forgery | No external payment API exposed | Add signed webhook verification and replay protection with a real gateway |

## Implemented checklist

- [x] Registration, password hashing, signed expiring tokens and explicit role checks.
- [x] MFA enrollment/confirmation and single-use time-step verification.
- [x] No doctor/admin access without a verified-MFA token.
- [x] Clinical participant authorization; admins do not receive prescription access.
- [x] Prescription and TOTP field encryption; encrypted MFA idempotency response.
- [x] Shared transactional rate limiting and typed input validation.
- [x] Core domain mutation idempotency and database uniqueness safeguards.
- [x] Audit write/read events; PostgreSQL append-only row trigger.
- [x] Secrets generated locally, excluded from Git and image build context.
- [x] Container runs non-root; API read-only filesystem/capability drop in Compose.
- [x] Security/dependency scanning is configured and packaging results are recorded.

## Production release gates (not represented as implemented)

- [ ] TLS termination, private DB TLS, managed encrypted disks/backups and KMS IAM.
- [ ] Managed secrets, runtime DB role without schema ownership/DDL and CI OIDC.
- [ ] MFA recovery with verified identity, secure password reset and email verification.
- [ ] Immediate session revocation/logout, token refresh policy and security notifications.
- [ ] Domain-appropriate consent, retention/deletion and verified subject-access workflow.
- [ ] External tamper-evident audit sink and alerting on privileged operations.
- [ ] Clinical/prescribing review, jurisdiction-specific regulatory/legal assessment.
- [ ] Live provider integration, signed callbacks and provider idempotency guarantees.
- [ ] Network/WAF limits and monitoring access controls; no public /metrics exposure.
- [ ] Independent security testing, restored-backup drill and measured load/HA results.

## Key rotation

JWT: set a fresh JWT_SECRET and move the previous value to JWT_PREVIOUS_SECRET. Deploy all
replicas together; old tokens verify until the previous secret is removed. Remove it after
the maximum token lifetime. Emergency removal invalidates its tokens immediately.

Fernet: put new ENCRYPTION_KEY first and retain old comma-separated keys in
ENCRYPTION_PREVIOUS_KEYS. The first key encrypts; all keys decrypt. Reencrypt prescription,
MFA-secret and MFA-idempotency ciphertext with MultiFernet.rotate in a reviewed migration.
Only remove old keys after verifying every row and backup recovery policy. The migration
is an operational procedure, not an automatic job in this submission. Losing keys loses data.

## Scope of compliance

Auditability and access controls support compliance; they do not certify it. Use synthetic
data in this assignment. Actual retention, consent and medical record rules depend on
where the service operates and must be assessed before handling real patient information.

## Frontend security additions

The browser portal uses same-origin fetch with bearer credentials held in tab memory only.
No external CDN, third-party font, analytics or client-side storage of credentials is used.
Refreshing signs out. Local sign-out clears the tab state but cannot revoke an already copied
JWT. UI role navigation is convenience only; all role/participant checks stay server-side.
Dynamic API values are HTML-escaped or inserted with textContent. The frontend root sends a
CSP restricting scripts/connect to self, with no objects/frames/base changes, plus no-referrer
and disabled camera/microphone/geolocation permissions. Inline style is allowed for progress
bars and layout snippets. The public Swagger documentation has its own assets/policy.
MFA seeds are displayed only during setup and cleared from DOM on dialog close; handle them
privately. No frontend mechanism can self-promote users to admin or doctor.
