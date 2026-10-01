"""Seed IntelliStock with reference records and six months of transactions."""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import (
    Customer,
    Product,
    Supplier,
    Transaction,
    TransactionType,
    User,
    Warehouse,
)


WAREHOUSE_DATA = (
    ("Central Depot", "Central District", 12000, 9400),
    ("East Hub", "East Industrial Park", 8000, 6100),
    ("West Hub", "West Logistics Zone", 8000, 5750),
)

SUPPLIER_DATA = (
    ("Northstar Electronics", "orders@northstarelectronics.example", "Net 30; weekly replenishment"),
    ("Summit Hardware", "sales@summithardware.example", "Net 30; twice-weekly delivery"),
    ("PackRight Supply", "orders@packright.example", "Net 15; minimum order applies"),
    ("OfficeSource Co.", "accounts@officesource.example", "Net 30; monthly catalog pricing"),
    ("SafeWork Industrial", "sales@safeworkindustrial.example", "Net 45; safety-certified stock"),
)

CUSTOMER_DATA = tuple(
    (name, f"{email_name}@example.com", phone)
    for name, email_name, phone in (
        ("Apex Retail Group", "apex.retail", "+1-555-0101"),
        ("Bluebird Market", "bluebird.market", "+1-555-0102"),
        ("Cedar Point Stores", "cedar.point", "+1-555-0103"),
        ("Delta Office Partners", "delta.office", "+1-555-0104"),
        ("Evergreen Hardware", "evergreen.hardware", "+1-555-0105"),
        ("Foxglove Supply", "foxglove.supply", "+1-555-0106"),
        ("Granite Bay Trading", "granite.bay", "+1-555-0107"),
        ("Harborview Goods", "harborview.goods", "+1-555-0108"),
        ("Ironwood Commerce", "ironwood.commerce", "+1-555-0109"),
        ("Juniper Lane Shops", "juniper.lane", "+1-555-0110"),
    )
)

PRODUCT_DATA = (
    ("ELEC-001", "Wireless Barcode Scanner", "Electronics", "89.99", 74, 15),
    ("ELEC-002", "USB-C Docking Station", "Electronics", "124.50", 48, 10),
    ("ELEC-003", "Thermal Label Printer", "Electronics", "219.00", 31, 8),
    ("ELEC-004", "Inventory Tablet 10-inch", "Electronics", "329.99", 26, 6),
    ("ELEC-005", "Wi-Fi Access Point", "Electronics", "139.95", 43, 10),
    ("ELEC-006", "Handheld RFID Reader", "Electronics", "279.00", 19, 5),
    ("HARD-001", "Cordless Drill 18V", "Hardware", "159.99", 52, 12),
    ("HARD-002", "Steel Socket Set", "Hardware", "48.75", 96, 20),
    ("HARD-003", "Adjustable Wrench 12-inch", "Hardware", "21.50", 118, 24),
    ("HARD-004", "Heavy-Duty Utility Knife", "Hardware", "12.99", 145, 30),
    ("HARD-005", "Worklight LED 2000lm", "Hardware", "39.95", 67, 14),
    ("HARD-006", "Measuring Tape 8m", "Hardware", "14.25", 132, 28),
    ("PACK-001", "Corrugated Box Medium", "Packaging", "1.35", 820, 180),
    ("PACK-002", "Corrugated Box Large", "Packaging", "2.10", 610, 140),
    ("PACK-003", "Bubble Wrap Roll 50m", "Packaging", "18.90", 94, 20),
    ("PACK-004", "Stretch Film 500mm", "Packaging", "9.75", 156, 35),
    ("PACK-005", "Packing Tape Clear 6-pack", "Packaging", "11.40", 204, 45),
    ("PACK-006", "Padded Mailer 25-pack", "Packaging", "16.25", 88, 20),
    ("OFF-001", "Copy Paper A4 5-ream", "Office Supplies", "27.99", 124, 25),
    ("OFF-002", "Permanent Marker 12-pack", "Office Supplies", "8.49", 178, 36),
    ("OFF-003", "Thermal Labels 1000-roll", "Office Supplies", "22.50", 103, 22),
    ("OFF-004", "Desktop Calculator", "Office Supplies", "19.95", 61, 14),
    ("OFF-005", "Clipboard A4 6-pack", "Office Supplies", "13.80", 79, 18),
    ("OFF-006", "Shipping Document Pouch", "Office Supplies", "7.25", 210, 48),
    ("SAFE-001", "Nitrile Gloves Large 100-pack", "Safety", "12.75", 166, 36),
    ("SAFE-002", "Safety Glasses Clear", "Safety", "6.95", 142, 30),
    ("SAFE-003", "High-Visibility Vest", "Safety", "18.50", 57, 12),
    ("SAFE-004", "First Aid Kit 50-person", "Safety", "64.00", 24, 6),
    ("SAFE-005", "Ear Protection Muffs", "Safety", "24.95", 44, 10),
    ("SAFE-006", "Cut-Resistant Gloves Pair", "Safety", "15.99", 92, 20),
)

CATEGORY_SUPPLIER = {
    "Electronics": "Northstar Electronics",
    "Hardware": "Summit Hardware",
    "Packaging": "PackRight Supply",
    "Office Supplies": "OfficeSource Co.",
    "Safety": "SafeWork Industrial",
}

TARGET_TRANSACTION_COUNT = 360


def _ensure_warehouses(db: Session) -> tuple[dict[str, Warehouse], int]:
    warehouses = {warehouse.name: warehouse for warehouse in db.query(Warehouse).all()}
    created = 0
    for name, location, total_capacity, available_capacity in WAREHOUSE_DATA:
        if name not in warehouses:
            warehouse = Warehouse(
                name=name,
                location=location,
                total_capacity=total_capacity,
                available_capacity=available_capacity,
            )
            db.add(warehouse)
            warehouses[name] = warehouse
            created += 1
    db.flush()
    return warehouses, created


def _ensure_suppliers(db: Session) -> tuple[dict[str, Supplier], int]:
    suppliers = {supplier.name: supplier for supplier in db.query(Supplier).all()}
    created = 0
    for name, contact_email, supply_terms in SUPPLIER_DATA:
        if name not in suppliers:
            supplier = Supplier(
                name=name,
                contact_email=contact_email,
                supply_terms=supply_terms,
            )
            db.add(supplier)
            suppliers[name] = supplier
            created += 1
    db.flush()
    return suppliers, created


def _ensure_customers(db: Session) -> int:
    customer_emails = {
        customer.contact_email for customer in db.query(Customer).all()
    }
    created = 0
    for name, contact_email, phone in CUSTOMER_DATA:
        if contact_email not in customer_emails:
            db.add(Customer(name=name, contact_email=contact_email, phone=phone))
            created += 1
    db.flush()
    return created


def _ensure_products(
    db: Session,
    warehouses: dict[str, Warehouse],
    suppliers: dict[str, Supplier],
) -> tuple[list[Product], int]:
    products = {product.sku: product for product in db.query(Product).all()}
    created = 0
    warehouse_names = tuple(name for name, *_ in WAREHOUSE_DATA)
    for index, (sku, name, category, price, stock, reorder_threshold) in enumerate(
        PRODUCT_DATA
    ):
        if sku not in products:
            warehouse = warehouses[warehouse_names[index % len(warehouse_names)]]
            supplier = suppliers[CATEGORY_SUPPLIER[category]]
            product = Product(
                sku=sku,
                name=name,
                category=category,
                unit_price=price,
                stock_quantity=stock,
                reorder_threshold=reorder_threshold,
                warehouse_id=warehouse.id,
                supplier_id=supplier.id,
            )
            db.add(product)
            products[sku] = product
            created += 1
    db.flush()
    return list(products.values()), created


def _create_transactions(db: Session, products: list[Product]) -> int:
    existing_count = db.query(Transaction).count()
    missing_count = max(0, TARGET_TRANSACTION_COUNT - existing_count)
    if missing_count == 0 or not products:
        return 0

    rng = random.Random(20261001)
    now = datetime.now(timezone.utc)
    events: list[Transaction] = []
    for index in range(missing_count):
        day_offset = index % 180
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=day_offset
        )
        latest_second = min(86399, int((now - day_start).total_seconds()))
        timestamp = day_start + timedelta(seconds=rng.randint(0, latest_second))
        transaction_type = (
            TransactionType.PURCHASE
            if index % 2 == 1 and day_offset % 4 != 0
            else TransactionType.SALE
        )
        product = rng.choice(products)
        quantity = rng.randint(12, 80) if transaction_type == TransactionType.PURCHASE else rng.randint(1, 16)
        events.append(
            Transaction(
                product_id=product.id,
                warehouse_id=product.warehouse_id,
                type=transaction_type,
                quantity=quantity,
                timestamp=timestamp,
            )
        )

    db.add_all(events)
    return len(events)


def seed_data(db: Session) -> dict[str, int]:
    """Create missing demo records and bring transaction history to 360 rows."""
    init_db(db)
    try:
        warehouses, warehouse_count = _ensure_warehouses(db)
        suppliers, supplier_count = _ensure_suppliers(db)
        customer_count = _ensure_customers(db)
        products, product_count = _ensure_products(db, warehouses, suppliers)
        transaction_count = _create_transactions(db, products)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "warehouses_created": warehouse_count,
        "suppliers_created": supplier_count,
        "customers_created": customer_count,
        "products_created": product_count,
        "transactions_created": transaction_count,
        "warehouses_total": db.query(Warehouse).count(),
        "suppliers_total": db.query(Supplier).count(),
        "customers_total": db.query(Customer).count(),
        "products_total": db.query(Product).count(),
        "transactions_total": db.query(Transaction).count(),
        "admins_total": db.query(User).filter(User.email == "admin@intellistock.com").count(),
    }


def main() -> None:
    with SessionLocal() as db:
        results = seed_data(db)
    for name, count in results.items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()