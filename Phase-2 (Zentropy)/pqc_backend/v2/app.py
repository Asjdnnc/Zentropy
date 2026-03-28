"""
QuantumGuard v2 — FastAPI Application Entry Point
===================================================
Starts the multi-user custodial wallet server.

To run:
    python -m pqc_backend.v2.app
    # or
    uvicorn pqc_backend.v2.app:app --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_DOTENV_PATH, override=True)


# ── Application ──────────────────────────────────────────

app = FastAPI(
    title="QuantumGuard Custodial Wallet API",
    description=(
        "Multi-user post-quantum cryptographic wallet system. "
        "Uses Dilithium (ML-DSA-44) signatures with Merkle-batched "
        "transaction proofs committed to Starknet."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "https://zentropy-steel.vercel.app",
    ).split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Logging ──────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("quantumguard")

# ── Lifecycle ────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """Initialize database pool and run migrations on startup."""
    from .db.connection import get_pool
    from .db.migrations import run_migrations

    logger.info("QuantumGuard v2 starting up …")
    logger.info("Effective STARKNET_RPC: %s", os.environ.get("STARKNET_RPC", "UNSET"))
    await get_pool()
    await run_migrations()
    logger.info("QuantumGuard v2 ready — multi-user custodial mode")


@app.on_event("shutdown")
async def shutdown():
    """Close database pool on shutdown."""
    from .db.connection import close_pool

    logger.info("QuantumGuard v2 shutting down …")
    await close_pool()


# ── Register Routes ──────────────────────────────────────

from .api.routes import router as v2_router

app.include_router(v2_router)


# Also mount the v1 server at /api/v1 for backward compatibility
# (optional — can be removed when migration is complete)
@app.get("/")
async def root():
    return {
        "service": "QuantumGuard Custodial Wallet",
        "version": "2.0.0",
        "docs": "/docs",
        "api_base": "/api/v2",
    }


# ── CLI Entry Point ──────────────────────────────────────

def main():
    import uvicorn

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))

    logger.info("Starting QuantumGuard v2 on %s:%d", host, port)
    uvicorn.run(
        "pqc_backend.v2.app:app",
        host=host,
        port=port,
        reload=os.environ.get("ENV", "development") == "development",
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
