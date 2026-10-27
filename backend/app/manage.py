"""Administrative CLI. Never expose role promotion as a public endpoint."""

import argparse
from sqlalchemy import select
from app.db import Base, engine, SessionLocal
from app.models import User, Audit

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["init-db", "promote-admin"])
parser.add_argument("--email")
args = parser.parse_args()
if args.command == "init-db":
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as c:
            c.exec_driver_sql(
                """CREATE OR REPLACE FUNCTION deny_audit_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'audit logs are append-only'; END; $$ LANGUAGE plpgsql"""
            )
            c.exec_driver_sql("DROP TRIGGER IF EXISTS audit_immutable ON audit_logs")
            c.exec_driver_sql(
                "CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION deny_audit_mutation()"
            )
else:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email).with_for_update())
        if not user or not user.mfa_enabled:
            raise SystemExit("Register and enable MFA first")
        user.role = "admin"
        db.add(Audit(actor_id="operator", action="promoted_admin", resource_id=user.id))
        db.commit()
        print("Admin promoted. Log in again with a fresh MFA code.")
