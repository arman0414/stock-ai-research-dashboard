from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stock_ai.api.routes import router
from stock_ai.db.session import init_db


app = FastAPI(
    title="Stock AI Dashboard API",
    version="0.1.0",
    description="Phase 1 API for watchlist management and historical market-data storage.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "stock-ai-dashboard"}


app.include_router(router)

