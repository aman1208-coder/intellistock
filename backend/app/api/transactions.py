from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import Product, Transaction, TransactionType, User, Warehouse
from app.schemas.transaction import TransactionCreate, TransactionRead


router = APIRouter(prefix="/api/transactions", tags=["Transactions"])
MANAGER_ROLES = ["ADMIN", "WAREHOUSE_MANAGER"]


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    product_id: Optional[int] = Query(default=None, gt=0),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Transaction]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be before end_date")
    query = db.query(Transaction)
    if product_id is not None:
        query = query.filter(Transaction.product_id == product_id)
    if start_date is not None:
        query = query.filter(Transaction.timestamp >= start_date)
    if end_date is not None:
        query = query.filter(Transaction.timestamp <= end_date)
    return query.order_by(Transaction.timestamp.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> Transaction:
    product = db.scalar(
        select(Product).where(Product.id == payload.product_id).with_for_update()
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    warehouse = db.scalar(
        select(Warehouse).where(Warehouse.id == payload.warehouse_id).with_for_update()
    )
    if warehouse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    if product.warehouse_id != warehouse.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product is not assigned to this warehouse")

    if payload.type == TransactionType.PURCHASE:
        if payload.quantity > warehouse.available_capacity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase exceeds available warehouse capacity")
        product.stock_quantity += payload.quantity
        warehouse.available_capacity -= payload.quantity
    else:
        if payload.quantity > product.stock_quantity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sale exceeds available stock")
        if warehouse.available_capacity + payload.quantity > warehouse.total_capacity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sale would exceed warehouse capacity")
        product.stock_quantity -= payload.quantity
        warehouse.available_capacity += payload.quantity

    transaction = Transaction(**payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction