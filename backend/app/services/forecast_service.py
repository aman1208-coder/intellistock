"""Database orchestration for demand forecasts and reorder analysis."""

from __future__ import annotations

import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_models.forecasting import forecast_daily_demand

from app.models import (
    Product,
    ReorderLog,
    ReorderStatus,
    Transaction,
    TransactionType,
)


HISTORY_DAYS = 180
ANNUAL_HOLDING_RATE = 0.25
ORDERING_COST = 50.0
FORECAST_MODEL_NAME = "Ridge regression with weekday and lag features"


class ProductNotFoundError(LookupError):
    """Raised when no product exists for the requested forecast."""


def _validate_parameters(
    horizon_days: int,
    lead_time_days: int,
    service_level: float,
) -> None:
    if not 1 <= horizon_days <= 30:
        raise ValueError("horizon_days must be between 1 and 30.")
    if not 1 <= lead_time_days <= 90:
        raise ValueError("lead_time_days must be between 1 and 90.")
    if not 0.5 < service_level < 0.999:
        raise ValueError("service_level must be greater than 0.5 and less than 0.999.")


def _daily_sales(
    db: Session,
    product_id: int,
    as_of: date,
) -> pd.Series:
    start_date = as_of - timedelta(days=HISTORY_DAYS - 1)
    start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)
    if db.get_bind().dialect.name == "sqlite":
        start_at = start_at.replace(tzinfo=None)
        end_at = end_at.replace(tzinfo=None)

    rows = (
        db.query(Transaction.timestamp, Transaction.quantity)
        .filter(
            Transaction.product_id == product_id,
            Transaction.type == TransactionType.SALE,
            Transaction.timestamp >= start_at,
            Transaction.timestamp < end_at,
        )
        .all()
    )
    totals: dict[date, int] = {}
    for timestamp, quantity in rows:
        transaction_date = (
            timestamp.astimezone(timezone.utc).date()
            if timestamp.tzinfo is not None
            else timestamp.date()
        )
        totals[transaction_date] = totals.get(transaction_date, 0) + quantity

    dates = pd.date_range(start=start_date, end=as_of, freq="D")
    return pd.Series(
        [totals.get(timestamp.date(), 0) for timestamp in dates],
        index=dates,
        dtype=float,
    )


def _build_forecast(
    db: Session,
    product: Product,
    horizon_days: int,
    lead_time_days: int,
    service_level: float,
    as_of: date,
) -> dict:
    daily_sales = _daily_sales(db, product.id, as_of)
    predictions = forecast_daily_demand(daily_sales, horizon_days)

    average_daily_demand = float(daily_sales.mean())
    demand_std_dev = float(daily_sales.std(ddof=1)) if len(daily_sales) > 1 else 0.0
    z_score = NormalDist().inv_cdf(service_level)
    safety_stock = z_score * demand_std_dev * math.sqrt(lead_time_days)
    reorder_point = average_daily_demand * lead_time_days + safety_stock

    annual_demand = average_daily_demand * 365
    annual_holding_cost = max(float(product.unit_price) * ANNUAL_HOLDING_RATE, 0.01)
    eoq = (
        math.sqrt((2 * annual_demand * ORDERING_COST) / annual_holding_cost)
        if annual_demand > 0
        else 0.0
    )
    recommended_order_quantity = max(1, int(round(eoq)))
    should_reorder = product.stock_quantity <= reorder_point
    first_forecast_date = as_of + timedelta(days=1)

    return {
        "product_id": product.id,
        "sku": product.sku,
        "product_name": product.name,
        "model": FORECAST_MODEL_NAME,
        "history_days": HISTORY_DAYS,
        "horizon_days": horizon_days,
        "current_stock": product.stock_quantity,
        "average_daily_demand": round(average_daily_demand, 3),
        "demand_std_dev": round(demand_std_dev, 3),
        "lead_time_days": lead_time_days,
        "service_level": service_level,
        "safety_stock": round(safety_stock, 2),
        "reorder_point": round(reorder_point, 2),
        "recommended_order_quantity": recommended_order_quantity,
        "forecast_total_demand": round(float(np.sum(predictions)), 2),
        "should_reorder": should_reorder,
        "daily_forecast": [
            {
                "date": (first_forecast_date + timedelta(days=offset)).isoformat(),
                "predicted_demand": round(max(0.0, float(value)), 2),
            }
            for offset, value in enumerate(predictions)
        ],
    }


def forecast_product(
    db: Session,
    product_id: int,
    horizon_days: int = 14,
    lead_time_days: int = 7,
    service_level: float = 0.95,
    as_of: date | None = None,
) -> dict:
    """Return a daily demand forecast and inventory planning metrics."""
    _validate_parameters(horizon_days, lead_time_days, service_level)
    product = db.get(Product, product_id)
    if product is None:
        raise ProductNotFoundError("Product not found.")
    return _build_forecast(
        db,
        product,
        horizon_days,
        lead_time_days,
        service_level,
        as_of or datetime.now(timezone.utc).date(),
    )


def run_reorder_analysis(
    db: Session,
    horizon_days: int = 14,
    lead_time_days: int = 7,
    service_level: float = 0.95,
    as_of: date | None = None,
) -> dict:
    """Forecast every product and create missing pending reorder suggestions."""
    _validate_parameters(horizon_days, lead_time_days, service_level)
    analysis_date = as_of or datetime.now(timezone.utc).date()
    products = db.query(Product).order_by(Product.id).with_for_update().all()
    pending_product_ids = {
        product_id
        for (product_id,) in db.query(ReorderLog.product_id)
        .filter(ReorderLog.status == ReorderStatus.PENDING)
        .all()
    }
    forecasts: list[dict] = []
    reorders_created = 0
    try:
        for product in products:
            forecast = _build_forecast(
                db,
                product,
                horizon_days,
                lead_time_days,
                service_level,
                analysis_date,
            )
            forecasts.append(forecast)
            if forecast["should_reorder"] and product.id not in pending_product_ids:
                reason = (
                    f"Ridge forecast: average daily demand "
                    f"{forecast['average_daily_demand']:.3f}; demand standard deviation "
                    f"{forecast['demand_std_dev']:.3f}; lead time {lead_time_days} days; "
                    f"safety stock {forecast['safety_stock']:.2f}; reorder point "
                    f"{forecast['reorder_point']:.2f}; current stock {product.stock_quantity}."
                )
                db.add(
                    ReorderLog(
                        product_id=product.id,
                        suggested_qty=forecast["recommended_order_quantity"],
                        reason=reason,
                        status=ReorderStatus.PENDING,
                    )
                )
                pending_product_ids.add(product.id)
                reorders_created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "products_analyzed": len(products),
        "reorders_created": reorders_created,
        "forecasts": forecasts,
    }