"""Administrator-only member management endpoints."""

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, require_role
from app.db.session import get_db
from app.models import User
from app.schemas.user import PasswordResetResponse, UserAdminRead


router = APIRouter(prefix="/api/users", tags=["User management"])
logger = logging.getLogger(__name__)
ADMIN = Depends(require_role(["ADMIN"]))


def _audit(actor: User, action: str, target: User) -> None:
    logger.info(
        "Account audit actor_user_id=%s action=%s target_user_id=%s at=%s",
        actor.id,
        action,
        target.id,
        datetime.now(timezone.utc).isoformat(),
    )


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=list[UserAdminRead])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = ADMIN,
) -> list[User]:
    return db.query(User).order_by(User.id).all()


@router.patch("/{user_id}/deactivate", response_model=UserAdminRead)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = ADMIN,
) -> User:
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account",
        )
    user.is_active = False
    db.commit()
    db.refresh(user)
    _audit(admin, "deactivated", user)
    return user


@router.patch("/{user_id}/activate", response_model=UserAdminRead)
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = ADMIN,
) -> User:
    user = _get_user(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/{user_id}/reset-password",
    response_model=PasswordResetResponse,
)
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = ADMIN,
) -> PasswordResetResponse:
    user = _get_user(db, user_id)
    temporary_password = secrets.token_urlsafe(24)
    user.hashed_password = get_password_hash(temporary_password)
    db.commit()
    _audit(admin, "password_reset", user)
    return PasswordResetResponse(temporary_password=temporary_password)
