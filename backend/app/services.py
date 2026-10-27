"""Shared transaction helpers, durable replay, audit and distributed rate limiting."""

import hashlib, json, time
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from app.db import get_db
from app.models import Audit, Idempotency, RateBucket
from app.security import encrypt, decrypt


def audit(db, user, action, resource):
    db.add(Audit(actor_id=user.id, action=action, resource_id=str(resource)))


def lock(db, key):
    if db.bind.dialect.name == "postgresql":
        n = int.from_bytes(
            hashlib.sha256(key.encode()).digest()[:8], "big", signed=True
        )
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": n})


def rate_limit(request: Request, db=Depends(get_db)):
    # Shared atomic PostgreSQL bucket: 120 requests/minute/IP, 10 for auth.
    bucket = int(time.time()) // 60
    auth = request.url.path.startswith("/auth/")
    key = hashlib.sha256(f"{request.client.host}:{bucket}:{auth}".encode()).hexdigest()
    lock(db, "rate:" + key)
    row = db.get(RateBucket, key)
    if row is None:
        row = RateBucket(
            key=key,
            count=0,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(row)
    row.count += 1
    count = row.count
    db.commit()
    if count > (10 if auth else 120):
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})


def write(db, user, key, operation, body, run, secret=False):
    if not key or not 8 <= len(key) <= 128:
        raise HTTPException(400, "Idempotency-Key header must contain 8-128 characters")
    scoped = hashlib.sha256(f"{user}:{key}".encode()).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps([operation, body], sort_keys=True, default=str).encode()
    ).hexdigest()
    lock(db, "idem:" + scoped)
    prior = db.get(Idempotency, scoped)
    if prior:
        if prior.fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency key reused for a different request")
        return json.loads(
            decrypt(prior.response[10:])
            if prior.response.startswith("encrypted:")
            else prior.response
        )
    result = run()
    db.add(
        Idempotency(
            key=scoped,
            fingerprint=fingerprint,
            response=("encrypted:" + encrypt(json.dumps(result)))
            if secret
            else json.dumps(result),
        )
    )
    db.commit()
    return result
