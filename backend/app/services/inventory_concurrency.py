"""Inventory sale operations with and without row-level locking."""

from sqlalchemy import update
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
    """Deduct stock safely using the active database's concurrency primitive."""
    if quantity <= 0:
        raise ValueError("Sale quantity must be greater than zero.")

    if db.get_bind().dialect.name == "sqlite":
        try:
            # SQLite has no row-level SELECT FOR UPDATE. The predicate and
            # decrement execute atomically while SQLite serializes the writer.
            result = db.execute(
                update(Product)
                .where(
                    Product.id == product_id,
                    Product.stock_quantity >= quantity,
                )
                .values(stock_quantity=Product.stock_quantity - quantity)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 0:
                if db.get(Product, product_id) is None:
                    raise ProductNotFoundException("Product not found.")
                raise InsufficientStockException("Sale exceeds available stock.")

            product = db.get(Product, product_id)
            if product is None:
                raise ProductNotFoundException("Product not found.")
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
        except Exception:
            db.rollback()
            raise

    # Preserve PostgreSQL's row-level lock implementation.
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
