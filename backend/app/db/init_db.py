"""Create the database schema and ensure a default administrator exists."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base_class import Base
from app.db.session import engine
from app.models import User, UserRole


def init_db(db: Session) -> None:
    Base.metadata.create_all(bind=engine)

    admin_password = settings.initial_admin_password
    admin = db.query(User).filter(User.email == "admin@intellistock.com").first()
    if admin is None and admin_password and admin_password.get_secret_value():
        db.add(
            User(
                email="admin@intellistock.com",
                username="admin",
                hashed_password=get_password_hash(admin_password.get_secret_value()),
                role=UserRole.ADMIN,
                is_active=True,
            )
        )
        db.commit()


__all__ = ["init_db"]