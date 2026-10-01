from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.ai import router as ai_router
from app.api.concurrency import router as concurrency_router
from app.api.products import router as products_router
from app.api.transactions import router as transactions_router
from app.api.warehouses import router as warehouses_router
from app.db.init_db import init_db
from app.db.session import SessionLocal


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as db:
        init_db(db)
    yield


app = FastAPI(title="IntelliStock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(concurrency_router)
app.include_router(products_router)
app.include_router(warehouses_router)
app.include_router(transactions_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "IntelliStock API"}