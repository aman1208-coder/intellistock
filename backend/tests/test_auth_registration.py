"""Registration authorization tests using isolated SQLite storage."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.auth import router
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base_class import Base
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
        cls.app.include_router(router)

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
                hashed_password="not-used-by-these-tests",
                role=UserRole.STAFF,
                is_active=True,
            )
            db.add_all([self.admin, self.staff])
            db.commit()
            db.refresh(self.admin)
            db.refresh(self.staff)
            self.admin_token = create_access_token(self.admin.id)
            self.staff_token = create_access_token(self.staff.id)

    def tearDown(self) -> None:
        settings.allow_public_registration = self.previous_public_registration

    @staticmethod
    def payload(**extra: object) -> dict[str, object]:
        result: dict[str, object] = {
            "email": "new-user@example.test",
            "username": "new-user",
            "password": "a-long-test-password",
        }
        result.update(extra)
        return result

    def test_anonymous_registration_is_rejected_by_default(self) -> None:
        response = self.client.post("/api/auth/register", json=self.payload())

        self.assertEqual(response.status_code, 401, response.text)
        with self.SessionLocal() as db:
            self.assertIsNone(db.query(User).filter_by(username="new-user").first())

    def test_admin_can_create_user_as_staff(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json=self.payload(),
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["role"], UserRole.STAFF.value)

    def test_request_cannot_choose_role(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json=self.payload(role=UserRole.ADMIN.value),
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )

        self.assertEqual(response.status_code, 422, response.text)
        with self.SessionLocal() as db:
            self.assertIsNone(db.query(User).filter_by(username="new-user").first())

    def test_public_opt_in_creates_staff_only(self) -> None:
        settings.allow_public_registration = True

        response = self.client.post("/api/auth/register", json=self.payload())

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["role"], UserRole.STAFF.value)

    def test_staff_cannot_create_users_when_public_registration_is_off(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json=self.payload(),
            headers={"Authorization": f"Bearer {self.staff_token}"},
        )

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
