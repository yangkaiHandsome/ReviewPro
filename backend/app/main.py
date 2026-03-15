from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes_audit import router as audit_router
from app.api.routes_documents import router as documents_router
from app.api.routes_health import router as health_router
from app.api.routes_strategies import router as strategies_router
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.logging_config import configure_logging
from app.models import Rule, Strategy
from app.services.audit_worker import AuditWorker

logger = logging.getLogger(__name__)


def _seed_default_strategy(db: Session) -> None:
    existing = db.scalar(select(Strategy).limit(1))
    if existing is not None:
        return

    strategy = Strategy(id=str(uuid4()), name="Default Technical Document Strategy")
    strategy.rules = [
        Rule(
            id="R001",
            title="Glossary Coverage",
            description="The document should include glossary, terms, or abbreviations.",
            severity="medium",
            is_required=True,
        ),
        Rule(
            id="R002",
            title="Version Traceability",
            description="The document should include version history or revision log.",
            severity="high",
            is_required=True,
        ),
        Rule(
            id="R003",
            title="Conclusion Section",
            description="The document should include conclusion or recommendation section.",
            severity="medium",
            is_required=False,
        ),
    ]
    db.add(strategy)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting application. api_prefix=%s storage_dir=%s", settings.api_prefix, settings.storage_dir)
    init_db()
    logger.info("Database initialized.")
    with SessionLocal() as db:
        _seed_default_strategy(db)
    logger.info("Default strategy seed check completed.")

    worker = AuditWorker(SessionLocal, settings)
    worker.start()
    app.state.audit_worker = worker
    logger.info("Audit worker started.")
    yield
    logger.info("Stopping audit worker.")
    worker.stop()
    logger.info("Application shutdown complete.")


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    started = time.perf_counter()
    logger.info("HTTP request started. method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception(
            "HTTP request failed. method=%s path=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "HTTP request completed. method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(strategies_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(audit_router, prefix=settings.api_prefix)
