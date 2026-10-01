"""Security and authentication utilities."""

import bcrypt


def get_password_hash(password: str) -> str:
	password_bytes = password.encode("utf-8")
	if len(password_bytes) > 72:
		raise ValueError("Bcrypt passwords must be no longer than 72 bytes.")
	return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
	try:
		return bcrypt.checkpw(
			plain_password.encode("utf-8"),
			hashed_password.encode("ascii"),
		)
	except (UnicodeEncodeError, ValueError):
		return False