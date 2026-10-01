"""Password hashing, JWT handling, and authenticated-user dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User, UserRole


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
	if len(password.encode("utf-8")) > 72:
		raise ValueError("Bcrypt passwords must be no longer than 72 bytes.")
	return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
	if len(plain_password.encode("utf-8")) > 72:
		return False
	try:
		return password_context.verify(plain_password, hashed_password)
	except (TypeError, ValueError):
		return False


def create_access_token(
	subject: Union[str, int],
	expires_delta: Optional[timedelta] = None,
) -> str:
	expires_at = datetime.now(timezone.utc) + (
		expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
	)
	return jwt.encode(
		{"sub": str(subject), "exp": expires_at},
		settings.secret_key,
		algorithm=settings.algorithm,
	)


def get_current_user(
	credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
	db: Session = Depends(get_db),
) -> User:
	unauthorized = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	if credentials is None:
		raise unauthorized

	try:
		payload = jwt.decode(
			credentials.credentials,
			settings.secret_key,
			algorithms=[settings.algorithm],
		)
		user_id = int(payload.get("sub", ""))
	except (JWTError, TypeError, ValueError):
		raise unauthorized from None

	user = db.get(User, user_id)
	if user is None or not user.is_active:
		raise unauthorized
	return user


def require_role(allowed_roles: Sequence[Union[str, UserRole]]) -> Callable:
	allowed_values = {
		role.value if isinstance(role, Enum) else role.upper()
		for role in allowed_roles
	}

	def role_dependency(current_user: User = Depends(get_current_user)) -> User:
		if current_user.role.value not in allowed_values:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="Insufficient permissions",
			)
		return current_user

	return role_dependency