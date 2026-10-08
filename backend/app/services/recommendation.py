"""Cross-sell recommendations based on concurrent purchase patterns."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models import Product, Transaction, TransactionType


def get_frequently_bought_together(
    db: Session,
    product_id: int,
    limit: int = 5,
) -> dict[str, Any]:
    """Return the products most often sold alongside the provided product."""
    product = db.get(Product, product_id)
    if product is None:
        raise LookupError("Product not found.")

    sales = (
        db.query(Transaction)
        .filter(Transaction.type == TransactionType.SALE)
        .all()
    )
    baskets_by_day_and_warehouse: dict[tuple[int, str], set[int]] = defaultdict(set)
    for sale in sales:
        basket_key = (sale.warehouse_id, sale.timestamp.date().isoformat())
        baskets_by_day_and_warehouse[basket_key].add(sale.product_id)

    pair_counts: dict[int, int] = defaultdict(int)
    for basket in baskets_by_day_and_warehouse.values():
        if product_id not in basket:
            continue
        related = basket - {product_id}
        for other_product in related:
            pair_counts[other_product] += 1

    recommendations: list[dict[str, Any]] = []
    for other_product_id, count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))[:limit]:
        other_product = db.get(Product, other_product_id)
        if other_product is None:
            continue
        recommendations.append(
            {
                "product_id": other_product.id,
                "product_name": other_product.name,
                "co_occurrence_count": count,
                "score": round(count / max(1, len(baskets_by_day_and_warehouse)), 3),
            }
        )

    return {
        "product_id": product.id,
        "product_name": product.name,
        "recommendations": recommendations,
    }
