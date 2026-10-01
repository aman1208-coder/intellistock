"""Demand forecasting and dynamic reorder endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import User
from app.schemas.forecast import DemandForecastRead, ReorderAnalysisRead
from app.services.forecast_service import (
    ProductNotFoundError,
    forecast_product,
    run_reorder_analysis,
)


router = APIRouter(prefix="/api/ai", tags=["AI Forecasting"])
MANAGER_ROLES = ["ADMIN", "WAREHOUSE_MANAGER"]


@router.get("/forecast/{product_id}", response_model=DemandForecastRead)
def get_product_forecast(
    product_id: int,
    horizon_days: int = Query(default=14, ge=1, le=30),
    lead_time_days: int = Query(default=7, ge=1, le=90),
    service_level: float = Query(default=0.95, gt=0.5, lt=0.999),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    try:
        return forecast_product(
            db,
            product_id,
            horizon_days=horizon_days,
            lead_time_days=lead_time_days,
            service_level=service_level,
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/run-reorder-analysis", response_model=ReorderAnalysisRead)
def analyze_reorders(
    horizon_days: int = Query(default=14, ge=1, le=30),
    lead_time_days: int = Query(default=7, ge=1, le=90),
    service_level: float = Query(default=0.95, gt=0.5, lt=0.999),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role(MANAGER_ROLES)),
) -> dict:
    try:
        return run_reorder_analysis(
            db,
            horizon_days=horizon_days,
            lead_time_days=lead_time_days,
            service_level=service_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc