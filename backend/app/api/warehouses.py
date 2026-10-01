from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import User, Warehouse
from app.schemas.warehouse import WarehouseCreate, WarehouseRead, WarehouseUpdate


router = APIRouter(prefix="/api/warehouses", tags=["Warehouses"])
MANAGER_ROLES = ["ADMIN", "WAREHOUSE_MANAGER"]


@router.get("", response_model=list[WarehouseRead])
def list_warehouses(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Warehouse]:
    return db.query(Warehouse).order_by(Warehouse.id).offset(skip).limit(limit).all()


@router.post("", response_model=WarehouseRead, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> Warehouse:
    warehouse = Warehouse(**payload.model_dump())
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return warehouse


@router.put("/{warehouse_id}", response_model=WarehouseRead)
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field is required")
    total_capacity = updates.get("total_capacity", warehouse.total_capacity)
    available_capacity = updates.get("available_capacity", warehouse.available_capacity)
    if available_capacity > total_capacity:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Available capacity cannot exceed total capacity")
    for field, value in updates.items():
        setattr(warehouse, field, value)
    db.commit()
    db.refresh(warehouse)
    return warehouse