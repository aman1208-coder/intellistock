"""Forecast and dynamic reorder tests using isolated SQLite storage."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
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

from app.core.security import get_current_user
from app.db.base_class import Base
from app.db.session import get_db
from app.models import (
    Product,
    ReorderLog,
    Supplier,
    Transaction,
    TransactionType,
    UserRole,
    Warehouse,
)
from app.services.forecast_service import forecast_product, run_reorder_analysis
from ml_models.forecasting import forecast_daily_demand


class ForecastServiceTests(unittest.TestCase):
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
            name=f"Forecast warehouse {suffix}",
            location="Test",
            total_capacity=1000,
            available_capacity=900,
        )
        self.supplier = Supplier(
            name=f"Forecast supplier {suffix}",
            contact_email=f"forecast-{suffix}@example.test",
            supply_terms="Test only",
        )
        self.db.add_all([self.warehouse, self.supplier])
        self.db.flush()
        self.product = Product(
            sku=f"FC-{suffix}",
            name="Forecast test product",
            category="Test",
            unit_price=25,
            stock_quantity=0,
            reorder_threshold=5,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
        )
        self.db.add(self.product)
        self.db.flush()
        self.product_id = self.product.id
        self.as_of = date(2026, 10, 1)
        for offset in range(60):
            transaction_date = self.as_of - timedelta(days=59 - offset)
            self.db.add(
                Transaction(
                    product_id=self.product.id,
                    warehouse_id=self.warehouse.id,
                    type=TransactionType.SALE,
                    quantity=2 + offset % 4,
                    timestamp=datetime.combine(
                        transaction_date,
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    ),
                )
            )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.query(ReorderLog).filter_by(product_id=self.product_id).delete()
        self.db.query(Transaction).filter_by(product_id=self.product_id).delete()
        self.db.query(Product).filter_by(id=self.product_id).delete()
        self.db.query(Warehouse).filter_by(id=self.warehouse.id).delete()
        self.db.query(Supplier).filter_by(id=self.supplier.id).delete()
        self.db.commit()
        self.db.close()

    def test_regression_forecast_is_finite_and_nonnegative(self) -> None:
        import pandas as pd

        dates = pd.date_range("2026-01-01", periods=90, freq="D")
        sales = pd.Series([3 + index % 7 for index in range(90)], index=dates)
        forecast = forecast_daily_demand(sales, horizon_days=21)
        self.assertEqual(len(forecast), 21)
        self.assertTrue(all(value >= 0 and value < 20 for value in forecast))

        short_sales = pd.Series([4.0] * 28, index=dates[:28])
        short_forecast = forecast_daily_demand(short_sales, horizon_days=14)
        self.assertEqual(short_forecast, [4.0] * 14)

    def test_forecast_and_reorder_run_are_idempotent(self) -> None:
        forecast = forecast_product(
            self.db,
            self.product_id,
            horizon_days=14,
            lead_time_days=7,
            as_of=self.as_of,
        )
        self.assertEqual(len(forecast["daily_forecast"]), 14)
        self.assertTrue(all(day["predicted_demand"] >= 0 for day in forecast["daily_forecast"]))
        self.assertGreater(forecast["average_daily_demand"], 0)
        self.assertGreater(forecast["reorder_point"], 0)
        self.assertGreater(forecast["recommended_order_quantity"], 0)

        first = run_reorder_analysis(self.db, as_of=self.as_of)
        second = run_reorder_analysis(self.db, as_of=self.as_of)
        self.assertEqual(first["products_analyzed"], 1)
        self.assertEqual(first["reorders_created"], 1)
        self.assertEqual(second["reorders_created"], 0)
        self.assertEqual(
            self.db.query(ReorderLog).filter_by(product_id=self.product_id).count(),
            1,
        )

    def test_forecast_endpoint_returns_seeded_product_prediction(self) -> None:
        from app.api.ai import get_product_forecast

        result = get_product_forecast(
            self.product_id,
            horizon_days=14,
            lead_time_days=7,
            service_level=0.95,
            db=self.db,
            _current_user=SimpleNamespace(role=UserRole.ADMIN),
        )
        self.assertEqual(result["sku"], self.product.sku)
        self.assertEqual(len(result["daily_forecast"]), 14)
        self.assertTrue(all(day["predicted_demand"] >= 0 for day in result["daily_forecast"]))


if __name__ == "__main__":
    unittest.main()