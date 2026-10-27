import os
import tempfile
from pathlib import Path
import pytest
from cryptography.fernet import Fernet

test_directory = tempfile.TemporaryDirectory(prefix="amrutam-tests-")
default_test_url = "sqlite:///" + (Path(test_directory.name) / "test.db").as_posix()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", default_test_url)
os.environ["JWT_SECRET"] = "test-secret-only-" * 4
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
from app.db import Base, engine, SessionLocal
from app.models import User, Profile, Doctor
from app.security import passwords, token
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def actors():
    result = {}
    with SessionLocal() as db:
        for name, role in [
            ("patient", "patient"),
            ("other", "patient"),
            ("doctor", "doctor"),
            ("admin", "admin"),
        ]:
            u = User(
                email=name + "@example.com",
                password_hash=passwords.hash("StrongPassword123!"),
                role=role,
                mfa_enabled=int(role != "patient"),
            )
            db.add(u)
            db.flush()
            db.add(Profile(user_id=u.id, name=name))
            if role == "doctor":
                db.add(Doctor(user_id=u.id, specialty="Ayurveda", fee_paise=50000))
            result[name] = {
                "id": u.id,
                "Authorization": "Bearer " + token(u, mfa=role != "patient"),
            }
        db.commit()
    return result
