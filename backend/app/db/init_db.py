"""Create the database schema and ensure a default administrator exists."""

from sqlalchemy import DateTime, inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base_class import Base
from app.db.session import engine
from app.models import User, UserRole


def _ensure_user_created_at(db: Session) -> None:
    bind = db.get_bind()
    if "created_at" not in {
        column["name"] for column in inspect(bind).get_columns(User.__tablename__)
    }:
        preparer = bind.dialect.identifier_preparer
        table_name = preparer.quote(User.__tablename__)
        column_name = preparer.quote("created_at")
        column_type = DateTime(timezone=True).compile(dialect=bind.dialect)
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
    table_name = bind.dialect.identifier_preparer.quote(User.__tablename__)
    column_name = bind.dialect.identifier_preparer.quote("created_at")
    db.execute(
        text(
            f"UPDATE {table_name} SET {column_name} = CURRENT_TIMESTAMP "
            f"WHERE {column_name} IS NULL"
        )
    )
    db.commit()


def init_db(db: Session) -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user_created_at(db)

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