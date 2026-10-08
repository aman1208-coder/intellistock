"""Natural-language stock insights backed by the live database."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Product, ReorderLog, ReorderStatus, Warehouse


def _normalize_question(question: str) -> str:
    return " ".join(question.lower().strip().split())


def _warehouse_capacity_summary(db: Session) -> list[dict[str, Any]]:
    rows = db.query(Warehouse).order_by(Warehouse.id).all()
    return [
        {
            "warehouse_id": warehouse.id,
            "name": warehouse.name,
            "location": warehouse.location,
            "total_capacity": warehouse.total_capacity,
            "available_capacity": warehouse.available_capacity,
        }
        for warehouse in rows
    ]


def _zero_stock_summary(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(Product)
        .filter(Product.stock_quantity == 0)
        .order_by(Product.id)
        .all()
    )
    return [
        {
            "product_id": product.id,
            "name": product.name,
            "stock_quantity": product.stock_quantity,
            "warehouse_id": product.warehouse_id,
        }
        for product in rows
    ]


def _threshold_warning_summary(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(Product)
        .filter(Product.stock_quantity <= Product.reorder_threshold)
        .order_by(Product.stock_quantity.asc(), Product.id.asc())
        .all()
    )
    return [
        {
            "product_id": product.id,
            "name": product.name,
            "stock_quantity": product.stock_quantity,
            "reorder_threshold": product.reorder_threshold,
            "warehouse_id": product.warehouse_id,
        }
        for product in rows
    ]


def _pending_reorder_summary(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(ReorderLog)
        .filter(ReorderLog.status == ReorderStatus.PENDING)
        .order_by(ReorderLog.generated_at.asc(), ReorderLog.id.asc())
        .all()
    )
    return [
        {
            "id": reorder.id,
            "product_id": reorder.product_id,
            "suggested_qty": reorder.suggested_qty,
            "reason": reorder.reason,
            "status": reorder.status.value,
        }
        for reorder in rows
    ]


def answer_stock_query(db: Session, question: str) -> dict[str, Any]:
    """Answer inventory questions using the current database state."""
    if not question or not question.strip():
        return {
            "answer": "Ask about zero-stock items, threshold warnings, warehouse capacity, or pending reorders.",
            "kind": "help",
            "items": [],
        }

    normalized = _normalize_question(question)
    zero_stock = _zero_stock_summary(db)
    threshold_items = _threshold_warning_summary(db)
    warehouse_capacity = _warehouse_capacity_summary(db)
    pending_reorders = _pending_reorder_summary(db)

    if any(token in normalized for token in ("zero", "out of stock", "out-of-stock", "empty")):
        answer = (
            f"{len(zero_stock)} item(s) are currently out of stock: "
            + ", ".join(item["name"] for item in zero_stock[:5])
            + (" ..." if len(zero_stock) > 5 else "")
            if zero_stock
            else "No product is currently zero stock."
        )
        return {
            "answer": answer,
            "kind": "zero_stock",
            "items": zero_stock,
        }

    if any(token in normalized for token in ("threshold", "warning", "low stock", "reorder")):
        answer = (
            f"{len(threshold_items)} product(s) are at or below their reorder threshold: "
            + ", ".join(item["name"] for item in threshold_items[:5])
            + (" ..." if len(threshold_items) > 5 else "")
            if threshold_items
            else "No items are currently below their reorder thresholds."
        )
        return {
            "answer": answer,
            "kind": "threshold_warning",
            "items": threshold_items,
        }

    if any(token in normalized for token in ("capacity", "warehouse", "space", "dock")):
        answer = (
            "Warehouse capacity overview: "
            + "; ".join(
                f"{warehouse['name']} has {warehouse['available_capacity']}/{warehouse['total_capacity']} available"
                for warehouse in warehouse_capacity
            )
        )
        return {
            "answer": answer,
            "kind": "capacity",
            "items": warehouse_capacity,
        }

    if any(token in normalized for token in ("pending reorder", "reorder backlog", "pending", "purchase order")):
        answer = (
            f"{len(pending_reorders)} pending reorder(s) are awaiting action." if pending_reorders else "There are no pending reorder records."
        )
        return {
            "answer": answer,
            "kind": "pending_reorders",
            "items": pending_reorders,
        }

    answer = (
        f"I checked the live inventory state: {len(zero_stock)} zero-stock item(s), "
        f"{len(threshold_items)} threshold-warning item(s), {len(warehouse_capacity)} warehouse(s), "
        f"and {len(pending_reorders)} pending reorder(s)."
    )
    return {
        "answer": answer,
        "kind": "overview",
        "items": {
            "zero_stock": zero_stock,
            "threshold_warning": threshold_items,
            "warehouse_capacity": warehouse_capacity,
            "pending_reorders": pending_reorders,
        },
    }
