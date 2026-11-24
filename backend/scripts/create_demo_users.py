"""Create or update local demo users without displaying their generated passwords."""

from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy import or_

from app.core.security import get_password_hash
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import User, UserRole


CREDENTIALS_FILE = Path(__file__).resolve().parents[1] / "demo_credentials.local.txt"
DEMO_USERS = {
    "demo_admin": (UserRole.ADMIN, "demo_admin@intellistock.local"),
    "demo_member": (UserRole.STAFF, "demo_member@intellistock.local"),
}


def load_or_create_passwords() -> dict[str, str]:
    passwords: dict[str, str] = {}
    if CREDENTIALS_FILE.exists():
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            username, separator, password = line.partition("=")
            if not separator or username not in DEMO_USERS or not password:
                raise ValueError(f"Invalid demo credentials file: {CREDENTIALS_FILE}")
            passwords[username] = password

    for username in DEMO_USERS:
        passwords.setdefault(username, secrets.token_urlsafe(24))

    CREDENTIALS_FILE.write_text(
        "".join(f"{username}={passwords[username]}\n" for username in DEMO_USERS),
        encoding="utf-8",
    )
    return passwords


def main() -> None:
    passwords = load_or_create_passwords()
    with SessionLocal() as db:
        init_db(db)
        for username, (role, email) in DEMO_USERS.items():
            user = db.query(User).filter(
                or_(User.username == username, User.email == email)
            ).first()
            if user is None:
                user = User(username=username, email=email, hashed_password="", role=role)
                db.add(user)
            elif user.username != username or user.email != email:
                raise ValueError(f"Demo account identity conflicts with an existing user: {username}")
            user.hashed_password = get_password_hash(passwords[username])
            user.role = role
            user.is_active = True
        db.commit()

    print("Demo users created or updated: demo_admin (ADMIN), demo_member (STAFF).")
    print(f"Credentials saved in {CREDENTIALS_FILE}.")


if __name__ == "__main__":
    main()
