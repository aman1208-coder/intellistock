"""Account-management authorization tests using isolated SQLite storage."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.core.validation import request_validation_exception_handler
from app.db.base_class import Base
from app.db.init_db import _ensure_user_created_at
from app.db.session import get_db
from app.models import User, UserRole


class RegistrationAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.app = FastAPI()
        cls.app.include_router(auth_router)
        cls.app.include_router(users_router)
        cls.app.add_exception_handler(
            RequestValidationError,
            request_validation_exception_handler,
        )

        def override_get_db():
            with cls.SessionLocal() as db:
                yield db

        cls.app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.engine.dispose()

    def setUp(self) -> None:
        self.previous_public_registration = settings.allow_public_registration
        settings.allow_public_registration = False
        with self.SessionLocal() as db:
            db.query(User).delete()
            self.admin = User(
                email="admin@example.test",
                username="admin",
                hashed_password="not-used-by-these-tests",
                role=UserRole.ADMIN,
                is_active=True,
            )
            self.staff = User(
                email="staff@example.test",
                username="staff",
                hashed_password=get_password_hash("staff-test-password-123"),
                role=UserRole.STAFF,
                is_active=True,
            )
            self.manager = User(
                email="manager@example.test",
                username="manager",
                hashed_password="not-used-by-these-tests",
                role=UserRole.WAREHOUSE_MANAGER,
                is_active=True,
            )
            db.add_all([self.admin, self.staff, self.manager])
            db.commit()
            db.refresh(self.admin)
            db.refresh(self.staff)
            db.refresh(self.manager)
            self.admin_token = create_access_token(self.admin.id)
            self.staff_token = create_access_token(self.staff.id)
            self.manager_token = create_access_token(self.manager.id)

    def tearDown(self) -> None:
        settings.allow_public_registration = self.previous_public_registration

    @staticmethod
    def payload(**extra: object) -> dict[str, object]:
        result: dict[str, object] = {
            "email": "new-user@example.test",
            "username": "new-user",
            "password": "a-strong-test-password",
        }
        result.update(extra)
        return result

    @staticmethod
    def headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_anonymous_registration_is_rejected_by_default(self) -> None:
        response = self.client.post("/api/auth/register", json=self.payload())

        self.assertEqual(response.status_code, 401)
        with self.SessionLocal() as db:
            self.assertIsNone(db.query(User).filter_by(username="new-user").first())

    def test_public_registration_setting_never_allows_anonymous_creation(self) -> None:
        settings.allow_public_registration = True
        response = self.client.post("/api/auth/register", json=self.payload())

        self.assertEqual(response.status_code, 401)

    def test_admin_can_create_user_as_staff_without_exposing_credentials(self) -> None:
        with self.assertLogs("app.api.auth", level="INFO") as audit:
            response = self.client.post(
                "/api/auth/register",
                json=self.payload(),
                headers=self.headers(self.admin_token),
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], UserRole.STAFF.value)
        self.assertIn("action=created", "\n".join(audit.output))
        self.assertNotIn("a-strong-test-password", "\n".join(audit.output))
        self.assertNotIn("hashed_password", response.json())
        self.assertNotIn("password", response.json())
        self.assertIn("created_at", response.json())

    def test_staff_and_manager_cannot_create_accounts(self) -> None:
        for token in (self.staff_token, self.manager_token):
            response = self.client.post(
                "/api/auth/register",
                json=self.payload(),
                headers=self.headers(token),
            )
            self.assertEqual(response.status_code, 403)

    def test_request_cannot_choose_role(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json=self.payload(role=UserRole.ADMIN.value),
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 422)
        self.assertNotIn("a-strong-test-password", response.text)
        with self.SessionLocal() as db:
            self.assertIsNone(db.query(User).filter_by(username="new-user").first())

    def test_duplicate_username_and_email_return_conflict(self) -> None:
        first = self.client.post(
            "/api/auth/register",
            json=self.payload(),
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(first.status_code, 201)

        duplicate_username = self.client.post(
            "/api/auth/register",
            json=self.payload(email="another@example.test"),
            headers=self.headers(self.admin_token),
        )
        duplicate_email = self.client.post(
            "/api/auth/register",
            json=self.payload(username="another-user"),
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(duplicate_username.status_code, 409)
        self.assertEqual(duplicate_email.status_code, 409)
        self.assertNotIn("new-user@example.test", duplicate_email.text)

    def test_weak_password_and_invalid_identity_return_validation_errors(self) -> None:
        weak_password = self.client.post(
            "/api/auth/register",
            json=self.payload(password="short"),
            headers=self.headers(self.admin_token),
        )
        invalid_username = self.client.post(
            "/api/auth/register",
            json=self.payload(username="bad username"),
            headers=self.headers(self.admin_token),
        )
        invalid_email = self.client.post(
            "/api/auth/register",
            json=self.payload(email="not-an-email"),
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(weak_password.status_code, 422)
        self.assertIn("12 characters", weak_password.text)
        self.assertNotIn("short", weak_password.text)
        self.assertEqual(invalid_username.status_code, 422)
        self.assertEqual(invalid_email.status_code, 422)

    def test_user_listing_is_admin_only_and_never_contains_hashes(self) -> None:
        self.assertEqual(self.client.get("/api/users").status_code, 401)
        for token in (self.staff_token, self.manager_token):
            response = self.client.get("/api/users", headers=self.headers(token))
            self.assertEqual(response.status_code, 403)
            deactivation = self.client.patch(
                f"/api/users/{self.staff.id}/deactivate",
                headers=self.headers(token),
            )
            reset = self.client.post(
                f"/api/users/{self.staff.id}/reset-password",
                headers=self.headers(token),
            )
            self.assertEqual(deactivation.status_code, 403)
            self.assertEqual(reset.status_code, 403)

        response = self.client.get(
            "/api/users",
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json())
        for account in response.json():
            self.assertEqual(
                set(account),
                {"id", "username", "email", "role", "is_active", "created_at"},
            )
            self.assertNotIn("hashed_password", account)

    def test_deactivated_user_cannot_log_in_or_use_existing_token(self) -> None:
        login = self.client.post(
            "/api/auth/login",
            json={"username": "staff", "password": "staff-test-password-123"},
        )
        self.assertEqual(login.status_code, 200)
        existing_token = login.json()["access_token"]

        with self.assertLogs("app.api.users", level="INFO") as audit:
            deactivated = self.client.patch(
                f"/api/users/{self.staff.id}/deactivate",
                headers=self.headers(self.admin_token),
            )
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["is_active"])
        self.assertIn("action=deactivated", "\n".join(audit.output))
        self.assertNotIn("staff-test-password-123", "\n".join(audit.output))

        denied_login = self.client.post(
            "/api/auth/login",
            json={"username": "staff", "password": "staff-test-password-123"},
        )
        denied_existing_token = self.client.get(
            "/api/users",
            headers=self.headers(existing_token),
        )
        self.assertEqual(denied_login.status_code, 401)
        self.assertEqual(denied_existing_token.status_code, 401)

        activated = self.client.patch(
            f"/api/users/{self.staff.id}/activate",
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()["is_active"])

    def test_admin_cannot_deactivate_self(self) -> None:
        response = self.client.patch(
            f"/api/users/{self.admin.id}/deactivate",
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 409)
        with self.SessionLocal() as db:
            self.assertTrue(db.get(User, self.admin.id).is_active)

    def test_reset_password_returns_one_time_password_and_audits_without_secrets(self) -> None:
        with self.assertLogs("app.api.users", level="INFO") as audit:
            response = self.client.post(
                f"/api/users/{self.staff.id}/reset-password",
                headers=self.headers(self.admin_token),
            )

        self.assertEqual(response.status_code, 200)
        temporary_password = response.json()["temporary_password"]
        self.assertGreaterEqual(len(temporary_password), 12)
        login = self.client.post(
            "/api/auth/login",
            json={"username": "staff", "password": temporary_password},
        )
        self.assertEqual(login.status_code, 200)
        audit_text = "\n".join(audit.output)
        self.assertIn("action=password_reset", audit_text)
        self.assertNotIn(temporary_password, audit_text)
        with self.SessionLocal() as db:
            self.assertNotIn(
                temporary_password,
                db.get(User, self.staff.id).hashed_password,
            )

    def test_existing_users_table_gets_created_at_without_losing_rows(self) -> None:
        legacy_engine = create_engine("sqlite://")
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
                "username VARCHAR(100) NOT NULL, hashed_password VARCHAR(255) NOT NULL, "
                "role VARCHAR(32) NOT NULL, is_active BOOLEAN NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, username, hashed_password, role, is_active) "
                "VALUES (1, 'legacy@example.test', 'legacy', 'hash', 'STAFF', 1)"
            )
        legacy_sessions = sessionmaker(bind=legacy_engine)
        try:
            with legacy_sessions() as db:
                _ensure_user_created_at(db)
                migrated = db.execute(
                    text("SELECT username, created_at FROM users WHERE id = 1")
                ).one()
                self.assertEqual(migrated.username, "legacy")
                self.assertIsNotNone(migrated.created_at)
                new_user = User(
                    email="new@example.test",
                    username="new-user",
                    hashed_password="hash",
                    role=UserRole.STAFF,
                    is_active=True,
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                self.assertIsNotNone(new_user.created_at)
        finally:
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
