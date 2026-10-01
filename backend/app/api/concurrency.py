"""Demonstration endpoints for safe and unsafe concurrent inventory sales."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.session import get_db
from app.models import User
from app.schemas.transaction import TransactionRead
from app.services.inventory_concurrency import (
    InsufficientStockException,
    ProductNotFoundException,
    transact_safe,
    transact_unsafe,
)


router = APIRouter(prefix="/api/inventory", tags=["Inventory Concurrency"])
MANAGER_ROLES = ["ADMIN", "WAREHOUSE_MANAGER"]


class InventorySaleRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


def _run_sale(sale, product_id: int, quantity: int, db: Session):
    try:
        return sale(db, product_id, quantity)
    except ProductNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InsufficientStockException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/transact-safe",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def transact_safe_endpoint(
    payload: InventorySaleRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
):
    return _run_sale(transact_safe, payload.product_id, payload.quantity, db)


@router.post(
    "/transact-unsafe",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def transact_unsafe_endpoint(
    payload: InventorySaleRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
):
    return _run_sale(transact_unsafe, payload.product_id, payload.quantity, db)