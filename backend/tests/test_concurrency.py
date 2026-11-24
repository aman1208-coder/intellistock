"""PostgreSQL integration tests for inventory row-lock behavior."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
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


class InventoryConcurrencySqliteTests(unittest.TestCase):
    """Check transactional stock invariants; SQLite does not provide row locks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="intellistock-concurrency-")
        database_path = Path(cls.temp_dir.name) / "concurrency.sqlite3"
        cls.engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        with self.SessionLocal() as db:
            warehouse = Warehouse(
                name=f"SQLite Race Warehouse {id(self)}",
                location="Concurrency Test",
                total_capacity=10,
                available_capacity=9,
            )
            supplier = Supplier(
                name=f"SQLite Race Supplier {id(self)}",
                contact_email=f"sqlite-race-{id(self)}@example.test",
                supply_terms="Test only",
            )
            db.add_all([warehouse, supplier])
            db.flush()
            product = Product(
                sku=f"SQLITE-RACE-{id(self)}",
                name="SQLite concurrency invariant item",
                category="Test",
                unit_price=1,
                stock_quantity=1,
                reorder_threshold=0,
                warehouse_id=warehouse.id,
                supplier_id=supplier.id,
            )
            db.add(product)
            db.commit()
            self.product_id = product.id
            self.warehouse_id = warehouse.id
            self.supplier_id = supplier.id

    def tearDown(self) -> None:
        with self.SessionLocal() as db:
            db.query(Transaction).filter_by(product_id=self.product_id).delete()
            db.query(Product).filter_by(id=self.product_id).delete()
            db.query(Warehouse).filter_by(id=self.warehouse_id).delete()
            db.query(Supplier).filter_by(id=self.supplier_id).delete()
            db.commit()

    def test_safe_sale_rejects_overdraft_and_preserves_stock(self) -> None:
        with self.SessionLocal() as db:
            with self.assertRaises(InsufficientStockException):
                transact_safe(db, self.product_id, 2)

        with self.SessionLocal() as db:
            product = db.get(Product, self.product_id)
            transaction_count = db.query(Transaction).filter_by(
                product_id=self.product_id
            ).count()
            self.assertEqual(product.stock_quantity, 1)
            self.assertEqual(transaction_count, 0)

    def test_eight_parallel_safe_sqlite_sales_decrement_and_record_once(self) -> None:
        with self.SessionLocal() as db:
            product = db.get(Product, self.product_id)
            product.stock_quantity = 8
            db.commit()

        def attempt_sale(_index: int) -> bool:
            with self.SessionLocal() as db:
                try:
                    transact_safe(db, self.product_id, 1)
                    return True
                except InsufficientStockException:
                    return False

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt_sale, range(8)))

        self.assertEqual(sum(results), 8)
        with self.SessionLocal() as db:
            product = db.get(Product, self.product_id)
            transaction_count = db.query(Transaction).filter_by(
                product_id=self.product_id
            ).count()
            self.assertEqual(product.stock_quantity, 0)
            self.assertEqual(transaction_count, 8)

    def test_failed_safe_sale_rolls_back_stock_and_transaction(self) -> None:
        def fail_transaction_flush(session, _flush_context, _instances) -> None:
            if any(isinstance(item, Transaction) for item in session.new):
                raise RuntimeError("simulated transaction-record failure")

        event.listen(Session, "before_flush", fail_transaction_flush)
        try:
            with self.SessionLocal() as db:
                with self.assertRaisesRegex(
                    RuntimeError, "simulated transaction-record failure"
                ):
                    transact_safe(db, self.product_id, 1)
        finally:
            event.remove(Session, "before_flush", fail_transaction_flush)

        with self.SessionLocal() as db:
            product = db.get(Product, self.product_id)
            transaction_count = db.query(Transaction).filter_by(
                product_id=self.product_id
            ).count()
            self.assertEqual(product.stock_quantity, 1)
            self.assertEqual(transaction_count, 0)

    def test_unsafe_path_keeps_read_then_write_without_row_lock(self) -> None:
        source = inspect.getsource(transact_unsafe)
        self.assertIn("db.query(Product).filter(Product.id == product_id).first()", source)
        self.assertIn("_record_sale(db, product, quantity)", source)
        self.assertNotIn("with_for_update", source)


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
