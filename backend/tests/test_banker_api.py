"""HTTP-level tests for Banker's warehouse allocation responses."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.concurrency import router
from app.core.security import get_current_user
from app.db.base_class import Base
from app.db.session import get_db
from app.models import UserRole, Warehouse
from app.services.banker import reset_warehouse_state


class BankerAllocationApiTests(unittest.TestCase):
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
        cls.current_user = SimpleNamespace(role=UserRole.ADMIN)
        cls.app.dependency_overrides[get_current_user] = lambda: cls.current_user
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.SessionLocal() as db:
            self.warehouse = Warehouse(
                name=f"Banker API {id(self)}",
                location="Test",
                total_capacity=100,
                available_capacity=90,
            )
            db.add(self.warehouse)
            db.commit()
            db.refresh(self.warehouse)
            self.warehouse_id = self.warehouse.id

    def tearDown(self) -> None:
        reset_warehouse_state(self.warehouse_id)
        with self.SessionLocal() as db:
            db.query(Warehouse).filter_by(id=self.warehouse_id).delete()
            db.commit()

    def _payload(self, process_id: str, *, max_docks: int = 5, max_equipment: int = 4, request_docks: int = 2, request_equipment: int = 2) -> dict:
        return {
            "warehouse_id": self.warehouse_id,
            "process_id": process_id,
            "total_resources": {"capacity": 100, "dock_bays": 12, "equipment": 9},
            "available_resources": {"capacity": 90, "dock_bays": 5, "equipment": 4},
            "max_claim": {"capacity": 30, "dock_bays": max_docks, "equipment": max_equipment},
            "request_vector": {"capacity": 4, "dock_bays": request_docks, "equipment": request_equipment},
        }

    def test_safe_allocation_returns_200_and_safe_sequence(self) -> None:
        response = self.client.post(
            "/api/inventory/allocate-warehouse-slot",
            json=self._payload("safe-process"),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["allocated"])
        self.assertEqual(response.json()["safe_sequence"], ["safe-process"])

    def test_unsafe_but_valid_allocation_returns_409(self) -> None:
        response = self.client.post(
            "/api/inventory/allocate-warehouse-slot",
            json=self._payload("unsafe-process", max_docks=7, max_equipment=6),
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("unsafe state", response.json()["detail"]["message"])

    def test_request_over_max_claim_returns_422(self) -> None:
        response = self.client.post(
            "/api/inventory/allocate-warehouse-slot",
            json=self._payload("over-claim", max_docks=7, max_equipment=6, request_docks=8),
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_reset_route_is_admin_only(self) -> None:
        type(self).current_user = SimpleNamespace(role=UserRole.WAREHOUSE_MANAGER)
        try:
            response = self.client.post(f"/api/inventory/reset-warehouse-state/{self.warehouse_id}")
        finally:
            type(self).current_user = SimpleNamespace(role=UserRole.ADMIN)

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()