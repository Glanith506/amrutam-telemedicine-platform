import time
from datetime import datetime, timedelta, timezone
import jwt, pyotp
from cryptography.fernet import Fernet, MultiFernet
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.db import get_db
from app.models import User

passwords = PasswordHash.recommended()
cipher = MultiFernet(
    [
        Fernet(k)
        for k in [settings.encryption_key]
        + settings.encryption_previous_keys.split(",")
        if k
    ]
)
bearer = HTTPBearer(auto_error=False)


def encrypt(s):
    return cipher.encrypt(s.encode()).decode()


def decrypt(s):
    return cipher.decrypt(s.encode()).decode()


def token(user, mfa=False):
    return jwt.encode(
        {
            "sub": user.id,
            "mfa": mfa,
            "iss": "amrutam",
            "aud": "amrutam-api",
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=settings.token_minutes),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def current_user(
    auth: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)
):
    if not auth:
        raise HTTPException(401, "Authentication required")
    payload = None
    for key in [settings.jwt_secret, settings.jwt_previous_secret]:
        if not key:
            continue
        try:
            payload = jwt.decode(
                auth.credentials,
                key,
                algorithms=["HS256"],
                audience="amrutam-api",
                issuer="amrutam",
                options={"require": ["sub", "exp", "iss", "aud"]},
            )
            break
        except jwt.InvalidTokenError:
            pass
    if payload is None:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, payload["sub"])
    if not user:
        raise HTTPException(401, "Unknown user")
    if (user.role in ("doctor", "admin") or user.mfa_enabled) and not payload.get(
        "mfa"
    ):
        raise HTTPException(403, "MFA verified login required")
    return user


def role(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, "Insufficient permission")


def verify_otp(user, code):
    step = int(time.time()) // 30
    if (
        not user.mfa_secret
        or not code
        or not pyotp.TOTP(decrypt(user.mfa_secret)).verify(code, valid_window=0)
        or user.last_totp >= step
    ):
        raise HTTPException(401, "Invalid or replayed MFA code")
    user.last_totp = step
