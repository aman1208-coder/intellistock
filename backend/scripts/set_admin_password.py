"""Create or reset the `admin` account so you can log in.

Usage (from the backend folder, with the same DATABASE_URL / .env the API uses):
    python -m scripts.set_admin_password "YourStrongPassword123"
"""
import sys

from sqlalchemy import or_

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models import User
from app.models.user import UserRole


def main() -> None:
    if len(sys.argv) != 2 or len(sys.argv[1]) < 8:
        sys.exit('Usage: python -m scripts.set_admin_password "<password of 8+ characters>"')
    db = SessionLocal()
    try:
        user = db.query(User).filter(or_(User.username == "admin", User.email == "admin@intellistock.com")).first()
        if user is None:
            user = User(username="admin", email="admin@intellistock.com", hashed_password="", role=UserRole.ADMIN)
            db.add(user)
        user.hashed_password = get_password_hash(sys.argv[1])
        user.role = UserRole.ADMIN
        user.is_active = True
        db.commit()
        print("admin password set. Log in as: admin")
    finally:
        db.close()


if __name__ == "__main__":
    main()