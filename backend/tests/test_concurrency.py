"""PostgreSQL integration tests for inventory row-lock behavior."""

from __future__ import annotations

import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base_class import Base
from app.models import Product, Supplier, Transaction, Warehouse
from app.services.inventory_concurrency import (
    InsufficientStockException,
    transact_safe,
    transact_unsafe,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
POSTGRES_TESTS_AVAILABLE = TEST_DATABASE_URL.startswith(
    ("postgresql://", "postgresql+")
)


@unittest.skipUnless(
    POSTGRES_TESTS_AVAILABLE,
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database.",
)
class InventoryConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            TEST_DATABASE_URL,
            pool_size=20,
            max_overflow=0,
            pool_pre_ping=True,
        )
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("Concurrency tests require PostgreSQL row locks.")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def setUp(self) -> None:
        self.db = self.SessionLocal()
        self.warehouse = Warehouse(
            name=f"Race Warehouse {id(self)}",
            location="Concurrency Test",
            total_capacity=100,
            available_capacity=90,
        )
        self.supplier = Supplier(
            name=f"Race Supplier {id(self)}",
            contact_email=f"race-{id(self)}@example.test",
            supply_terms="Test only",
        )
        self.db.add_all([self.warehouse, self.supplier])
        self.db.flush()
        self.product = Product(
            sku=f"RACE-{id(self)}",
            name="Concurrency Test Item",
            category="Test",
            unit_price=1,
            stock_quantity=10,
            reorder_threshold=1,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
        )
        self.db.add(self.product)
        self.db.commit()
        self.product_id = self.product.id
        self.warehouse_id = self.warehouse.id
        self.supplier_id = self.supplier.id
        self.db.close()

    def tearDown(self) -> None:
        with self.SessionLocal() as db:
            db.query(Transaction).filter(
                Transaction.product_id == self.product_id
            ).delete(synchronize_session=False)
            db.query(Product).filter(Product.id == self.product_id).delete()
            db.query(Warehouse).filter(
                Warehouse.id == self.warehouse_id
            ).delete()
            db.query(Supplier).filter(Supplier.id == self.supplier_id).delete()
            db.commit()

    def _attempt_sale(self, operation) -> bool:
        with self.SessionLocal() as db:
            try:
                operation(db, self.product_id, 1)
                return True
            except InsufficientStockException:
                return False

    def test_safe_mode_rejects_sales_beyond_stock(self) -> None:
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(lambda _: self._attempt_sale(transact_safe), range(20)))

        self.assertEqual(sum(results), 10)
        with self.SessionLocal() as db:
            product = db.get(Product, self.product_id)
            transactions = db.query(Transaction).filter_by(product_id=self.product_id).count()
            self.assertEqual(product.stock_quantity, 0)
            self.assertEqual(transactions, 10)

    def test_unsafe_mode_exposes_lost_updates(self) -> None:
        read_barrier = Barrier(20)

        def synchronize_product_reads(_session, instance) -> None:
            if isinstance(instance, Product) and instance.id == self.product_id:
                read_barrier.wait(timeout=30)

        event.listen(Session, "loaded_as_persistent", synchronize_product_reads)
        try:
            with ThreadPoolExecutor(max_workers=20) as executor:
                results = list(
                    executor.map(
                        lambda _: self._attempt_sale(transact_unsafe),
                        range(20),
                    )
                )
        finally:
            event.remove(Session, "loaded_as_persistent", synchronize_product_reads)

        self.assertEqual(sum(results), 20)
        with self.SessionLocal() as db:
            product = db.get(Product, self.product_id)
            transactions = db.query(Transaction).filter_by(product_id=self.product_id).count()
            self.assertEqual(product.stock_quantity, 9)
            self.assertEqual(transactions, 20)


if __name__ == "__main__":
    unittest.main()