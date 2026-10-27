"""Transactional outbox worker; notification delivery is an explicit demo adapter."""

import logging, time, random
from datetime import timedelta
from sqlalchemy import select, delete
from app.db import SessionLocal
from app.models import Outbox, RateBucket, now

logging.basicConfig(level=logging.INFO)


def deliver(kind, resource_id, delivery_id):
    # Replace with an email provider adapter. Pass delivery_id as provider deduplication key.
    # No clinical data or patient email is written to logs.
    logging.info("demo_notification event=%s delivery_id=%s", kind, delivery_id)


def tick():
    with SessionLocal() as db:
        row = db.scalar(
            select(Outbox)
            .where(Outbox.status == "pending", Outbox.available_at <= now())
            .order_by(Outbox.available_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not row:
            return False
        try:
            deliver(row.kind, row.resource_id, row.id)
            row.status = "delivered"
        except Exception:
            row.attempts += 1
                        # Randomness is used only for retry timing.
            row.available_at = now() + timedelta(
                seconds=min(3600, 2**row.attempts) + random.uniform(0, 1)  # nosec B311
            )
            if row.attempts >= 8:
                row.status = "dead"
        db.commit()
        return True


if __name__ == "__main__":
    last_cleanup = 0
    while True:
        if time.monotonic() - last_cleanup > 60:
            with SessionLocal() as db:
                db.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
                db.commit()
            last_cleanup = time.monotonic()
        if not tick():
            time.sleep(1)
