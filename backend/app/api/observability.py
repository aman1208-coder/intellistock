from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import get_current_user
from app.models import User
from app.schemas.observability import (
    ObservabilityIngest,
    ObservabilityMetrics,
    ObservabilityStatus,
    SecurityEvent,
)
from app.services.observability import observability_store


router = APIRouter(prefix="/api/observability", tags=["Observability"])


@router.get("/status", response_model=ObservabilityStatus)
def get_status(_current_user: User = Depends(get_current_user)) -> dict:
    return observability_store.status()


@router.get("/metrics", response_model=ObservabilityMetrics)
def get_metrics(_current_user: User = Depends(get_current_user)) -> dict:
    return observability_store.snapshot()


@router.get("/db-latency")
def get_db_latency(_current_user: User = Depends(get_current_user)) -> dict:
    snapshot = observability_store.snapshot()
    return snapshot["db_latency"]


@router.get("/network")
def get_network(_current_user: User = Depends(get_current_user)) -> dict:
    snapshot = observability_store.snapshot()
    return snapshot["network"]


@router.get("/security-events", response_model=list[SecurityEvent])
def get_security_events(
    limit: int = Query(default=50, ge=1, le=500),
    severity: str | None = Query(default=None),
    _current_user: User = Depends(get_current_user),
) -> list[dict]:
    events = observability_store.security_events.snapshot(limit=limit)
    if severity:
        events = [event for event in events if event.get("severity") == severity.lower()]
    return list(reversed(events[-limit:]))


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest(
    payload: ObservabilityIngest,
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
) -> dict:
    if not settings.observability_ingest_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ingest secret is not configured")
    if x_ingest_secret != settings.observability_ingest_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest secret")
    observability_store.ingest(payload.model_dump())
    return {"accepted": True}
