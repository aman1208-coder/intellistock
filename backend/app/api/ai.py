"""Demand forecasting, chatbot, and recommendation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import Product, User
from app.schemas.forecast import DemandForecastRead, ReorderAnalysisRead
from app.services.chatbot import answer_stock_query
from app.services.forecast_service import (
    ProductNotFoundError,
    forecast_product,
    run_reorder_analysis,
)
from app.services.recommendation import get_frequently_bought_together


router = APIRouter(prefix="/api/ai", tags=["AI Forecasting"])
MANAGER_ROLES = ["ADMIN", "WAREHOUSE_MANAGER"]


class ChatbotRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


@router.post("/chatbot")
def chat_with_inventory_bot(
    payload: ChatbotRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    return answer_stock_query(db, payload.question)


@router.get("/recommendations/{product_id}")
def get_product_recommendations(
    product_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    try:
        if db.get(Product, product_id) is None:
            raise ProductNotFoundError("Product not found.")
        return get_frequently_bought_together(db, product_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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