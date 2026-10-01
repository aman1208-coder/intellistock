"""Inventory sale operations with and without row-level locking."""

from sqlalchemy.orm import Session

from app.models import Product, Transaction, TransactionType


class ProductNotFoundException(LookupError):
    """Raised when an inventory operation references a missing product."""


class InsufficientStockException(ValueError):
    """Raised when a sale requests more stock than is available."""


def _record_sale(db: Session, product: Product, quantity: int) -> Transaction:
    if quantity <= 0:
        raise ValueError("Sale quantity must be greater than zero.")
    if quantity > product.stock_quantity:
        raise InsufficientStockException("Sale exceeds available stock.")

    product.stock_quantity -= quantity
    transaction = Transaction(
        product_id=product.id,
        warehouse_id=product.warehouse_id,
        type=TransactionType.SALE,
        quantity=quantity,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def transact_safe(db: Session, product_id: int, quantity: int) -> Transaction:
    """Deduct stock while holding the product row lock through commit."""
    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .with_for_update()
            .first()
        )
        if product is None:
            raise ProductNotFoundException("Product not found.")
        return _record_sale(db, product, quantity)
    except Exception:
        db.rollback()
        raise


def transact_unsafe(db: Session, product_id: int, quantity: int) -> Transaction:
    """Deduct stock without locking, for demonstrating lost updates."""
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise ProductNotFoundException("Product not found.")
        return _record_sale(db, product, quantity)
    except Exception:
        db.rollback()
        raise