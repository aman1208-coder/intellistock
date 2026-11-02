"""Assistant endpoint and inventory query tests using isolated SQLite storage."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for import_path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.api.ai import chat_with_inventory_bot, get_product_recommendations
from app.api.auth import login
from app.core.security import get_password_hash
from app.db.base_class import Base
from app.main import app
from app.models import (
    Product,
    Supplier,
    Transaction,
    TransactionType,
    User,
    UserRole,
    Warehouse,
)
from app.schemas.assistant import ChatbotRequest
from app.schemas.user import LoginRequest


class AssistantApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.db = self.SessionLocal()
        suffix = str(id(self))
        self.warehouse = Warehouse(
            name=f"Assistant warehouse {suffix}",
            location="Test",
            total_capacity=100,
            available_capacity=70,
        )
        self.supplier = Supplier(
            name=f"Assistant supplier {suffix}",
            contact_email=f"assistant-{suffix}@example.test",
            supply_terms="Test only",
        )
        self.db.add_all([self.warehouse, self.supplier])
        self.db.flush()
        self.product = Product(
            sku=f"SKU-{suffix}",
            name="Assistant test product",
            category="Test",
            unit_price=10,
            stock_quantity=3,
            reorder_threshold=5,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
        )
        self.related_product = Product(
            sku=f"RELATED-{suffix}",
            name="Related test product",
            category="Test",
            unit_price=12,
            stock_quantity=10,
            reorder_threshold=2,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
        )
        self.db.add_all([self.product, self.related_product])
        self.db.flush()
        self.product_id = self.product.id
        self.related_product_id = self.related_product.id
        self.warehouse_id = self.warehouse.id
        self.supplier_id = self.supplier.id
        self.db.add_all(
            [
                Transaction(
                    product_id=product_id,
                    warehouse_id=self.warehouse.id,
                    type=TransactionType.SALE,
                    quantity=1,
                    timestamp=datetime(2026, 10, 1, tzinfo=timezone.utc),
                )
                for product_id in (self.product_id, self.related_product_id)
            ]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.query(Transaction).filter(
            Transaction.product_id.in_([self.product_id, self.related_product_id])
        ).delete(synchronize_session=False)
        self.db.query(Product).filter(
            Product.id.in_([self.product_id, self.related_product_id])
        ).delete(synchronize_session=False)
        self.db.query(Warehouse).filter_by(id=self.warehouse_id).delete()
        self.db.query(Supplier).filter_by(id=self.supplier_id).delete()
        self.db.commit()
        self.db.close()

    def test_chatbot_reports_product_status_by_sku(self) -> None:
        response = chat_with_inventory_bot(
            ChatbotRequest(question=f"What is the status of product {self.product.sku}?"),
            db=self.db,
            _current_user=SimpleNamespace(role=UserRole.ADMIN),
        )

        self.assertEqual(response["kind"], "product_status")
        self.assertEqual(response["items"][0]["sku"], self.product.sku)
        self.assertEqual(response["items"][0]["status"], "low_stock")
        self.assertEqual(response["items"][0]["stock_quantity"], 3)

    def test_chatbot_lists_threshold_warnings(self) -> None:
        response = chat_with_inventory_bot(
            ChatbotRequest(question="Which items are low in stock?"),
            db=self.db,
            _current_user=SimpleNamespace(role=UserRole.ADMIN),
        )

        self.assertEqual(response["kind"], "threshold_warning")
        self.assertIn(self.product.name, [item["name"] for item in response["items"]])

    def test_login_response_includes_authenticated_role(self) -> None:
        username = f"assistant-{id(self)}"
        user = User(
            email=f"{username}@example.test",
            username=username,
            hashed_password=get_password_hash("Assistant-test-password-1"),
            role=UserRole.WAREHOUSE_MANAGER,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        try:
            response = login(
                LoginRequest(username=username, password="Assistant-test-password-1"),
                self.db,
            )
            self.assertEqual(response.role, UserRole.WAREHOUSE_MANAGER)
            self.assertTrue(response.access_token)
        finally:
            self.db.delete(user)
            self.db.commit()

    def test_recommendations_return_co_purchased_items(self) -> None:
        response = get_product_recommendations(
            self.product_id,
            db=self.db,
            _current_user=SimpleNamespace(role=UserRole.ADMIN),
        )

        self.assertEqual(response["product_id"], self.product_id)
        self.assertEqual(response["recommendations"][0]["product_id"], self.related_product_id)
        self.assertEqual(response["recommendations"][0]["co_occurrence_count"], 1)

    def test_assistant_paths_are_published_in_openapi(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/chatbot/query", paths)
        self.assertIn("/api/recommendations/{product_id}", paths)


if __name__ == "__main__":
    unittest.main()