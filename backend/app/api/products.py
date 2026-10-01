from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import (
    Product,
    ReorderLog,
    Supplier,
    Transaction,
    TransactionType,
    User,
    Warehouse,
)
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate


router = APIRouter(prefix="/api/products", tags=["Products"])
MANAGER_ROLES = ["ADMIN", "WAREHOUSE_MANAGER"]


def _validate_references(db: Session, warehouse_id: int, supplier_id: int) -> None:
    if db.get(Warehouse, warehouse_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    if db.get(Supplier, supplier_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")


@router.get("", response_model=list[ProductRead])
def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    low_stock: bool = False,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Product]:
    query = db.query(Product)
    if low_stock:
        query = query.filter(Product.stock_quantity <= Product.reorder_threshold)
    return query.order_by(Product.id).offset(skip).limit(limit).all()


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> Product:
    _validate_references(db, payload.warehouse_id, payload.supplier_id)
    if db.query(Product).filter(Product.sku == payload.sku).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU is already in use")
    warehouse = db.scalar(
        select(Warehouse).where(Warehouse.id == payload.warehouse_id).with_for_update()
    )
    if payload.stock_quantity > warehouse.available_capacity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Initial stock exceeds available warehouse capacity")
    warehouse.available_capacity -= payload.stock_quantity
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field is required")
    warehouse_id = updates.get("warehouse_id", product.warehouse_id)
    supplier_id = updates.get("supplier_id", product.supplier_id)
    _validate_references(db, warehouse_id, supplier_id)
    if warehouse_id != product.warehouse_id and (
        product.stock_quantity > 0 or updates.get("stock_quantity", 0) > 0
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Move stock through a recorded inventory transaction before changing warehouses")
    sku = updates.get("sku")
    if sku and db.query(Product).filter(Product.sku == sku, Product.id != product_id).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU is already in use")
    new_stock_quantity = updates.get("stock_quantity", product.stock_quantity)
    stock_delta = new_stock_quantity - product.stock_quantity
    if stock_delta:
        warehouse = db.scalar(
            select(Warehouse)
            .where(Warehouse.id == product.warehouse_id)
            .with_for_update()
        )
        if stock_delta > warehouse.available_capacity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stock increase exceeds available warehouse capacity")
        warehouse.available_capacity -= stock_delta
        db.add(
            Transaction(
                product_id=product.id,
                warehouse_id=product.warehouse_id,
                type=TransactionType.PURCHASE if stock_delta > 0 else TransactionType.SALE,
                quantity=abs(stock_delta),
            )
        )
    for field, value in updates.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> Response:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.stock_quantity > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product with remaining stock cannot be deleted")
    has_history = (
        db.query(Transaction.id).filter(Transaction.product_id == product_id).first()
        or db.query(ReorderLog.id).filter(ReorderLog.product_id == product_id).first()
    )
    if has_history:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product has related history and cannot be deleted")
    db.delete(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product is referenced by other records") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)