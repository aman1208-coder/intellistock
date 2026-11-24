"""Natural-language stock insights backed by the live database."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Product, ReorderLog, ReorderStatus, Warehouse
from app.core.config import settings
from app.services.forecast_service import forecast_product
from app.services.observability import observability_store

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = PROJECT_ROOT / "ml_models" / "chatbot" / "model.joblib"
_classifier = None


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


def _product_status_summary(db: Session, question: str) -> dict[str, Any] | None:
    normalized = _normalize_question(question)
    products = db.query(Product).order_by(Product.id).all()
    product = next(
        (
            item
            for item in products
            if re.search(
                rf"(?<!\w){re.escape(item.sku.casefold())}(?!\w)",
                normalized,
            )
        ),
        None,
    )
    if product is None:
        return None

    stock_status = (
        "out_of_stock"
        if product.stock_quantity == 0
        else "low_stock"
        if product.stock_quantity <= product.reorder_threshold
        else "in_stock"
    )
    item = {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "stock_quantity": product.stock_quantity,
        "reorder_threshold": product.reorder_threshold,
        "warehouse_id": product.warehouse_id,
        "status": stock_status,
    }
    return {
        "answer": (
            f"{product.name} ({product.sku}) has {product.stock_quantity} unit(s) "
            f"in stock; its reorder threshold is {product.reorder_threshold}. "
            f"Status: {stock_status.replace('_', ' ')}."
        ),
        "kind": "product_status",
        "items": [item],
    }


def _load_classifier() -> Any | None:
    global _classifier
    if _classifier is not None:
        return _classifier
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib
        # joblib uses pickle; only load the fixed, repository-built artifact here.
        _classifier = joblib.load(MODEL_PATH)
    except Exception:
        _classifier = None
    return _classifier


def _classify_intent(question: str) -> tuple[str | None, float]:
    classifier = _load_classifier()
    if classifier is None:
        return None, 0.0
    try:
        pipeline = classifier.get("pipeline") if isinstance(classifier, dict) else classifier
        scores = pipeline.predict_proba([question])[0]
        best = int(scores.argmax())
        confidence = float(scores[best])
        if confidence < settings.chatbot_confidence_threshold:
            return None, confidence
        return str(pipeline.classes_[best]), confidence
    except Exception:
        try:
            pipeline = classifier.get("pipeline") if isinstance(classifier, dict) else classifier
            return str(pipeline.predict([question])[0]), 1.0
        except Exception:
            return None, 0.0


def _keyword_intent(normalized: str) -> str | None:
    if any(word in normalized for word in ("system health", "overall health", "how is the app")):
        return "system_health_overview"
    if any(word in normalized for word in ("suspicious", "security event", "activity")):
        return "security_events"
    if any(word in normalized for word in ("retransmit", "network", "tcp", "connection")):
        return "network_issues"
    if any(word in normalized for word in ("slow database", "db latency", "database slow", "p95")):
        return "slow_database"
    if any(word in normalized for word in ("app slow", "api latency", "request latency")):
        return "api_latency"
    if any(word in normalized for word in ("forecast", "run out", "14 days")):
        return "demand_forecast"
    if any(word in normalized for word in ("recommend", "bought together")):
        return "recommendation"
    if any(word in normalized for word in ("zero", "out of stock", "empty")):
        return "zero_stock"
    if any(word in normalized for word in ("threshold", "warning", "low stock", "reorder")):
        return "low_stock_threshold"
    if any(word in normalized for word in ("capacity", "warehouse", "dock")):
        return "warehouse_capacity"
    if any(word in normalized for word in ("pending", "purchase order", "reorder backlog")):
        return "pending_reorders"
    if re.search(r"\bsku\b|SKU-", normalized, re.I):
        return "product_status"
    if any(word in normalized for word in ("hello", "hi ", "hey")):
        return "greeting"
    return None


def _grounded_intent(db: Session, question: str, intent: str) -> dict[str, Any]:
    if intent == "greeting":
        return {"answer": "Hello. Ask me about live inventory or system-health metrics.", "kind": intent, "items": [], "sources": []}
    if intent in ("how_does_it_work", "out_of_scope"):
        answer = (
            "Banker's algorithm checks a safe resource sequence; row locking prevents lost updates; "
            "priority scheduling promotes urgent stockout jobs."
            if intent == "how_does_it_work"
            else "I can help with live inventory and system-health questions about stock, forecasts, DB latency, network issues, and security events."
        )
        return {"answer": answer, "kind": intent, "items": [], "sources": []}
    if intent == "zero_stock":
        items = _zero_stock_summary(db)
        answer = f"{len(items)} product(s) are currently out of stock." + (" " + ", ".join(item["name"] for item in items[:5]) if items else "")
        return {"answer": answer, "kind": "zero_stock", "items": items, "sources": ["db:products"]}
    if intent == "low_stock_threshold":
        items = _threshold_warning_summary(db)
        answer = f"{len(items)} product(s) are at or below their reorder threshold." + (" " + ", ".join(item["name"] for item in items[:5]) if items else "")
        return {"answer": answer, "kind": "threshold_warning", "items": items, "sources": ["db:products"]}
    if intent == "warehouse_capacity":
        items = _warehouse_capacity_summary(db)
        answer = "Warehouse capacity: " + "; ".join(f"{item['name']} has {item['available_capacity']}/{item['total_capacity']} available" for item in items) if items else "No warehouse capacity data is available."
        return {"answer": answer, "kind": "capacity", "items": items, "sources": ["db:warehouses"]}
    if intent == "pending_reorders":
        items = _pending_reorder_summary(db)
        answer = f"{len(items)} pending reorder(s) are awaiting action." if items else "There are no pending reorder records."
        return {"answer": answer, "kind": "pending_reorders", "items": items, "sources": ["db:reorder_logs"]}
    if intent == "product_status":
        status = _product_status_summary(db, question)
        if status:
            status["sources"] = ["db:products"]
            return status
        return {"answer": "I could not identify that product in the live database.", "kind": "product_status", "items": [], "sources": ["db:products"]}
    if intent == "demand_forecast":
        forecasts = []
        for product in db.query(Product).order_by(Product.id).all()[:20]:
            try:
                forecasts.append(forecast_product(db, product.id, horizon_days=14))
            except Exception:
                continue
        at_risk = [item for item in forecasts if item["should_reorder"]]
        answer = f"{len(at_risk)} of {len(forecasts)} forecasted product(s) should be reordered within 14 days." if forecasts else "No 14-day forecast data is currently available."
        return {"answer": answer, "kind": "demand_forecast", "items": at_risk, "sources": ["db:transactions", "forecast_service"]}
    if intent == "recommendation":
        return {"answer": "No recommendation was retrieved because no product identifier was provided.", "kind": "recommendation", "items": [], "sources": ["db:transactions"]}

    snapshot = observability_store.snapshot()
    db_latency = snapshot["db_latency"]
    network = snapshot["network"] or {}
    app_latency = snapshot["app_latency"]
    cpu = snapshot["cpu"] or {}
    events = observability_store.security_events.snapshot(limit=100)
    if intent == "slow_database":
        if not db_latency.get("available", db_latency.get("samples", 0) > 0):
            return {"answer": "Database latency is unavailable because no live DB timing samples have been recorded yet.", "kind": intent, "items": db_latency, "sources": ["fallback:db_latency"]}
        answer = f"Database latency is p50 {db_latency['p50_ms']:.1f} ms, p95 {db_latency['p95_ms']:.1f} ms, and p99 {db_latency['p99_ms']:.1f} ms; {db_latency['slow_query_count']} queries exceeded {db_latency['threshold_ms']} ms."
        return {"answer": answer, "kind": intent, "items": db_latency, "sources": ["ebpf:db_latency", "fallback:db_latency"]}
    if intent == "api_latency":
        return {"answer": f"App-level request latency is p50 {app_latency['p50_ms']:.1f} ms and p95 {app_latency['p95_ms']:.1f} ms across {app_latency['samples']} samples.", "kind": intent, "items": app_latency, "sources": ["app-middleware"]}
    if intent == "network_issues":
        if not network:
            return {"answer": "Network telemetry is unavailable in the active collector; no live TCP measurements have been received.", "kind": intent, "items": {}, "sources": []}
        return {"answer": f"TCP telemetry reports {network.get('retransmits', 0)} retransmits, {network.get('resets', 0)} resets, and {network.get('connection_failures', 0)} connection failures.", "kind": intent, "items": network, "sources": ["ebpf:network", "fallback:network"]}
    if intent == "security_events":
        counts = {severity: sum(1 for event in events if event.get("severity") == severity) for severity in ("critical", "high", "medium", "low")}
        return {"answer": f"Recent security events: {counts['critical']} critical, {counts['high']} high, {counts['medium']} medium, and {counts['low']} low.", "kind": intent, "items": counts, "sources": ["ebpf:security_events"]}
    if intent == "system_health_overview":
        if not db_latency.get("available", db_latency.get("samples", 0) > 0) and not app_latency.get("samples") and not cpu and not network:
            return {"answer": "System telemetry is not available yet. The fallback collector is active, but it has not recorded enough live request, database, CPU, or network samples.", "kind": intent, "items": snapshot, "sources": []}
        cpu_value = cpu.get("process_percent", "unavailable")
        likely = "database" if db_latency["p95_ms"] >= app_latency["p95_ms"] else "application/network"
        answer = f"The app p95 is {app_latency['p95_ms']:.1f} ms; DB p95 is {db_latency['p95_ms']:.1f} ms; CPU is {cpu_value}; TCP has {network.get('retransmits', 0)} retransmits. Based on these live values, the likely bottleneck is {likely}."
        return {"answer": answer, "kind": intent, "items": {"cpu": cpu, "db_latency": db_latency, "network": network, "app_latency": app_latency}, "sources": ["app-middleware", "ebpf:db_latency", "ebpf:network"]}
    return {"answer": "I can help with live inventory and system-health questions.", "kind": "help", "items": [], "sources": []}


def answer_stock_query(db: Session, question: str) -> dict[str, Any]:
    """Answer inventory and system-health questions using live data."""
    if not question or not question.strip():
        return {"answer": "Ask about live stock, forecasts, DB latency, network issues, or security events.", "kind": "help", "items": [], "sources": []}
    normalized = _normalize_question(question)
    intent, _confidence = _classify_intent(normalized)
    if intent is None:
        intent = _keyword_intent(normalized)
    if intent is None:
        intent = "out_of_scope"
    return _grounded_intent(db, normalized, intent)
