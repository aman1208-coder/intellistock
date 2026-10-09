from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./.intellistock_preflight.db")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "admin123")
os.environ.setdefault("SECRET_KEY", "preflight-secret-key-1234567890")

from fastapi.testclient import TestClient

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.main import app
from app.models import Product, Supplier, User, UserRole, Warehouse


def _seed_inventory() -> int:
    with SessionLocal() as db:
        db.query(Product).delete()
        db.query(Warehouse).delete()
        db.query(Supplier).delete()
        db.query(User).filter(User.username != "admin").delete()
        db.commit()

        warehouse = Warehouse(
            name="Smoke Warehouse",
            location="Preflight Lab",
            total_capacity=200,
            available_capacity=180,
        )
        supplier = Supplier(
            name="Smoke Supplier",
            contact_email="supplier@demo.local",
            supply_terms="Next-day delivery",
        )
        db.add_all([warehouse, supplier])
        db.commit()
        db.refresh(warehouse)
        db.refresh(supplier)

        product = Product(
            sku="SMK-001",
            name="Smoke Test Product",
            category="Inventory Demo",
            unit_price=Decimal("24.99"),
            stock_quantity=12,
            reorder_threshold=5,
            warehouse_id=warehouse.id,
            supplier_id=supplier.id,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product.id


def main() -> int:
    with SessionLocal() as db:
        init_db(db)

    product_id = _seed_inventory()

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200, health.text
        assert health.json()["status"] == "ok"

        register = client.post(
            "/api/auth/register",
            json={
                "username": "smoketestuser",
                "email": "smoketest@example.com",
                "password": "SecurePass123!",
            },
        )
        assert register.status_code == 201, register.text

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        warehouse_list = client.get("/api/warehouses", headers=headers)
        assert warehouse_list.status_code == 200, warehouse_list.text

        queue_job = client.post(
            "/api/inventory/queue-job",
            json={"job_type": "inventory_check", "product_id": product_id},
            headers=headers,
        )
        assert queue_job.status_code == 201, queue_job.text

        priority_queue = client.get("/api/inventory/priority-queue", headers=headers)
        assert priority_queue.status_code == 200, priority_queue.text
        assert isinstance(priority_queue.json(), list) and priority_queue.json()

        forecast = client.get(f"/api/ai/forecast/{product_id}", headers=headers)
        assert forecast.status_code == 200, forecast.text
        assert forecast.json()["sku"] == "SMK-001"

        recommendations = client.get(f"/api/ai/recommendations/{product_id}", headers=headers)
        assert recommendations.status_code == 200, recommendations.text
        assert "recommendations" in recommendations.json()

        chatbot = client.post(
            "/api/ai/chatbot",
            json={"question": "Which items are low stock?"},
            headers=headers,
        )
        assert chatbot.status_code == 200, chatbot.text
        assert "answer" in chatbot.json()

        safe_sale = client.post(
            "/api/inventory/transact-safe",
            json={"product_id": product_id, "quantity": 2},
            headers=headers,
        )
        assert safe_sale.status_code == 201, safe_sale.text
        assert safe_sale.json()["product_id"] == product_id

    print("PASS: pre-flight API smoke checks succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
