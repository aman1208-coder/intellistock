"""Banker's allocation, priority scheduling, and sale-concurrency endpoints."""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import Product, User, Warehouse
from app.services.banker import (
    configure_warehouse_resources,
    get_warehouse_state,
    request_allocation,
    reset_warehouse_state,
    rollback_allocation,
)
from app.services.priority_scheduler import (
    NORMAL_PRIORITY,
    priority_for_stock,
    priority_scheduler,
)
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


class ResourceVector(BaseModel):
    capacity: int = Field(ge=0)
    dock_bays: int = Field(ge=0)
    equipment: int = Field(ge=0)

    def as_vector(self) -> List[int]:
        return [self.capacity, self.dock_bays, self.equipment]


class WarehouseAllocationRequest(BaseModel):
    warehouse_id: int = Field(gt=0)
    process_id: str = Field(min_length=1, max_length=100)
    total_resources: ResourceVector
    available_resources: ResourceVector
    max_claim: ResourceVector
    request_vector: ResourceVector

    @model_validator(mode="after")
    def validate_resource_claims(self) -> "WarehouseAllocationRequest":
        total = self.total_resources.as_vector()
        available = self.available_resources.as_vector()
        maximum = self.max_claim.as_vector()
        request = self.request_vector.as_vector()
        if any(available[index] > total[index] for index in range(3)):
            raise ValueError("available resources cannot exceed total resources")
        if any(maximum[index] > total[index] for index in range(3)):
            raise ValueError("maximum claim cannot exceed total resources")
        if any(request[index] > maximum[index] for index in range(3)):
            raise ValueError("request cannot exceed maximum claim")
        return self


class WarehouseAllocationResponse(BaseModel):
    warehouse_id: int
    process_id: str
    allocated: bool
    available_resources: ResourceVector
    safe_sequence: List[str]


class QueueJobRequest(BaseModel):
    job_type: Literal["inventory_check", "routine_audit"]
    product_id: Optional[int] = Field(default=None, gt=0)


class PriorityJobResponse(BaseModel):
    id: str
    priority: int
    job_type: str
    product_id: Optional[int]
    description: str
    queued_at: str


_api_scheduler = priority_scheduler


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
    "/allocate-warehouse-slot",
    response_model=WarehouseAllocationResponse,
)
def allocate_warehouse_slot(
    payload: WarehouseAllocationRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> WarehouseAllocationResponse:
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == payload.warehouse_id)
        .with_for_update()
        .first()
    )
    if warehouse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    if payload.total_resources.capacity != warehouse.total_capacity:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Capacity total must match the warehouse")
    if payload.available_resources.capacity != warehouse.available_capacity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Available capacity is out of date")

    try:
        configure_warehouse_resources(
            warehouse.id,
            payload.total_resources.as_vector(),
            payload.available_resources.as_vector(),
        )
        allocated = request_allocation(
            warehouse.id,
            payload.request_vector.as_vector(),
            process_id=payload.process_id,
            max_claim=payload.max_claim.as_vector(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if not allocated:
        state = get_warehouse_state(warehouse.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Allocation denied because the request exceeds available resources or leaves an unsafe state",
                "safe_sequence": state["safe_sequence"] if state else [],
            },
        )

    capacity_request = payload.request_vector.capacity
    warehouse.available_capacity -= capacity_request
    try:
        db.commit()
    except Exception:
        db.rollback()
        rollback_allocation(warehouse.id, payload.process_id, payload.request_vector.as_vector())
        raise

    state = get_warehouse_state(warehouse.id)
    return WarehouseAllocationResponse(
        warehouse_id=warehouse.id,
        process_id=payload.process_id,
        allocated=True,
        available_resources=ResourceVector(**{
            "capacity": state["available"][0],
            "dock_bays": state["available"][1],
            "equipment": state["available"][2],
        }),
        safe_sequence=state["safe_sequence"],
    )


@router.get("/priority-queue", response_model=List[PriorityJobResponse])
def get_priority_queue(
    _current_user: User = Depends(get_current_user),
) -> List[PriorityJobResponse]:
    return [
        PriorityJobResponse(
            id=job.id,
            priority=job.priority,
            job_type=job.job_type,
            product_id=job.product_id,
            description=job.description,
            queued_at=job.queued_at.isoformat(),
        )
        for job in _api_scheduler.snapshot()
    ]


@router.post(
    "/queue-job",
    response_model=PriorityJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def queue_job(
    payload: QueueJobRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> PriorityJobResponse:
    if payload.job_type == "routine_audit":
        priority = NORMAL_PRIORITY
        description = "Routine inventory audit"
    else:
        if payload.product_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="product_id is required for an inventory check")
        product = db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        priority = priority_for_stock(product.stock_quantity, product.reorder_threshold)
        description = "Zero-stock replenishment" if priority == 1 else "Low-stock replenishment" if priority == 2 else "Inventory check"

    job = _api_scheduler.enqueue(
        priority=priority,
        job_type=payload.job_type,
        product_id=payload.product_id,
        description=description,
    )
    return PriorityJobResponse(
        id=job.id,
        priority=job.priority,
        job_type=job.job_type,
        product_id=job.product_id,
        description=job.description,
        queued_at=job.queued_at.isoformat(),
    )


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

@router.post("/reset-warehouse-state/{warehouse_id}")
def reset_warehouse_resources(
    warehouse_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(["ADMIN"])),
) -> dict:
    """Release every Banker's allocation for a warehouse so the safety demo can be repeated."""
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).with_for_update().first()
    if warehouse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    state = get_warehouse_state(warehouse_id)
    held = sum(vector[0] for vector in state["allocation"].values()) if state else 0
    reset_warehouse_state(warehouse_id)
    warehouse.available_capacity = min(warehouse.total_capacity, warehouse.available_capacity + held)
    db.commit()
    return {"warehouse_id": warehouse_id, "released_capacity": held, "available_capacity": warehouse.available_capacity}

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