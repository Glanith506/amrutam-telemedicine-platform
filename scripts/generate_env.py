from pathlib import Path
import secrets
from cryptography.fernet import Fernet

p = Path(".env")
if p.exists():
    raise SystemExit(".env already exists; refusing to overwrite keys")
p.write_text(
    "JWT_SECRET="
    + secrets.token_urlsafe(48)
    + "\nENCRYPTION_KEY="
    + Fernet.generate_key().decode()
    + "\nPOSTGRES_PASSWORD="
    + secrets.token_urlsafe(24)
    + "\n"
)
print("Created .env. Keep it private and back up encryption keys separately.")
