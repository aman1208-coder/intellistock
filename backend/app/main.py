from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi import Request

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.ai import assistant_router, router as ai_router
from app.api.concurrency import router as concurrency_router
from app.api.products import router as products_router
from app.api.transactions import router as transactions_router
from app.api.warehouses import router as warehouses_router
from app.db.init_db import init_db
from app.db.session import SessionLocal, active_database
from app.core.config import settings
from app.core.validation import request_validation_exception_handler
from app.api.observability import router as observability_router
from app.services.observability import observability_store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as db:
        init_db(db)
    yield


app = FastAPI(title="IntelliStock API", lifespan=lifespan)
app.add_exception_handler(
    RequestValidationError,
    request_validation_exception_handler,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_origin_regex=r"https://.*\.devtunnels\.ms",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ai_router)
app.include_router(assistant_router)
app.include_router(concurrency_router)
app.include_router(products_router)
app.include_router(warehouses_router)
app.include_router(transactions_router)
app.include_router(observability_router)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - started) * 1000
    route = request.scope.get("route")
    observability_store.record_request(getattr(route, "path", "unmatched"), latency_ms)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "IntelliStock API", "active_database": active_database}
