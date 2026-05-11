"""FastAPI app factory + uvicorn entry point.

Wires:
  - x402 paywall
  - Gemini analyst (Vertex AI / public Gemini API)
  - Irys trace sealer
  - Arc chain client (mock or live)
  - SQLAlchemy session
  - CORS for the dashboard
  - optional local facilitator
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.analyst import Analyst
from agent.trace import TraceSealer
from storage.db import init_db
from storage.irys import IrysClient

from .chain import ChainClient
from .facilitator import router as facilitator_router
from .routes import router as oracle_router
from .verify import router as verify_router
from .x402 import X402Paywall

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)

logger = logging.getLogger("rr.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.paywall = X402Paywall()
    app.state.analyst = Analyst()
    app.state.sealer = TraceSealer(IrysClient())
    app.state.chain = ChainClient()
    logger.info(
        "boot: paywall_mock=%s analyst_mock=%s sealer_mock=%s chain_mock=%s",
        app.state.paywall.mock,
        app.state.analyst.mock,
        app.state.sealer.uploader.mock,
        app.state.chain.mock,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ReasoningReceipt",
        version="0.1.0",
        description="x402-paywalled AI oracle for prediction markets.",
        lifespan=lifespan,
    )
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Accept-Payment", "X-Payment-Challenge"],
    )
    app.include_router(oracle_router)
    app.include_router(verify_router)
    if os.getenv("RR_LOCAL_FACILITATOR", "").lower() in {"1", "true", "yes"}:
        app.include_router(facilitator_router)
    return app


app = create_app()


def run() -> None:
    """Entry point for `rr-server` console script."""
    import uvicorn

    uvicorn.run(
        "server.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "").lower() in {"1", "true", "yes"},
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
