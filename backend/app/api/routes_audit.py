from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import AuditJob, AuditResult, Document, Strategy
from app.schemas import (
    AuditJobResponse,
    AuditRequest,
    AuditResultResponse,
    AuditSubmitResponse,
    ReviewPlan,
)


router = APIRouter(prefix="/audit", tags=["audit"])
logger = logging.getLogger(__name__)


def _parse_review_plan(raw: str | None) -> ReviewPlan | None:
    if not raw:
        return None
    try:
        return ReviewPlan.model_validate_json(raw)
    except Exception:
        return None


def _parse_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _job_response(db: Session, job: AuditJob) -> AuditJobResponse:
    result_stmt = select(AuditResult).where(AuditResult.job_id == job.id).order_by(AuditResult.created_at.asc())
    rows = list(db.scalars(result_stmt).all())
    results = [
        AuditResultResponse(
            id=row.id,
            rule_id=row.rule_id,
            page=row.page,
            bbox=json.loads(row.bbox),
            content=row.content,
            suggestion=row.suggestion,
            status=row.status,  # type: ignore[arg-type]
            severity=row.severity,  # type: ignore[arg-type]
        )
        for row in rows
    ]
    return AuditJobResponse(
        job_id=job.id,
        doc_id=job.doc_id,
        strategy_id=job.strategy_id,
        status=job.status,  # type: ignore[arg-type]
        progress=float(job.progress),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        review_plan=_parse_review_plan(job.review_plan_json),
        visited_pages=_parse_json_list(job.visited_pages_json),
        audit_log=_parse_json_list(job.audit_log),
        results=results,
    )


@router.post("", response_model=AuditSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_audit(
    payload: AuditRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuditSubmitResponse:
    logger.info("Submitting audit request. doc_id=%s strategy_id=%s", payload.doc_id, payload.strategy_id)
    document = db.get(Document, payload.doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    strategy = db.get(Strategy, payload.strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")

    job = AuditJob(doc_id=payload.doc_id, strategy_id=payload.strategy_id, status="pending", progress=0.0)
    db.add(job)
    db.commit()
    db.refresh(job)

    worker = request.app.state.audit_worker
    worker.enqueue(job.id)
    logger.info("Audit job enqueued. job_id=%s doc_id=%s strategy_id=%s", job.id, payload.doc_id, payload.strategy_id)
    return AuditSubmitResponse(job_id=job.id, status="pending", progress=0.0)


@router.get("/job/{job_id}", response_model=AuditJobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> AuditJobResponse:
    stmt = (
        select(AuditJob)
        .options(selectinload(AuditJob.results))
        .where(AuditJob.id == job_id)
    )
    job = db.scalar(stmt)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit job not found.")
    logger.info("Returning audit job. job_id=%s status=%s progress=%s", job.id, job.status, job.progress)
    return _job_response(db, job)


@router.get("/{doc_id}", response_model=AuditJobResponse)
def get_latest_document_audit(doc_id: str, db: Session = Depends(get_db)) -> AuditJobResponse:
    stmt = (
        select(AuditJob)
        .where(AuditJob.doc_id == doc_id)
        .order_by(AuditJob.created_at.desc())
        .limit(1)
    )
    job = db.scalar(stmt)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No audit job found for this document.",
        )
    logger.info("Returning latest audit for document. doc_id=%s job_id=%s status=%s", doc_id, job.id, job.status)
    return _job_response(db, job)


@router.post("/{doc_id}/retry", response_model=AuditSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_audit(doc_id: str, request: Request, db: Session = Depends(get_db)) -> AuditSubmitResponse:
    stmt = (
        select(AuditJob)
        .where(AuditJob.doc_id == doc_id)
        .order_by(AuditJob.created_at.desc())
        .limit(1)
    )
    previous = db.scalar(stmt)
    if previous is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audit job to retry.")

    job = AuditJob(
        doc_id=doc_id,
        strategy_id=previous.strategy_id,
        status="pending",
        progress=0.0,
        retry_count=previous.retry_count + 1,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    worker = request.app.state.audit_worker
    worker.enqueue(job.id)
    logger.info("Retry audit enqueued. new_job_id=%s doc_id=%s previous_job_id=%s", job.id, doc_id, previous.id)
    return AuditSubmitResponse(job_id=job.id, status="pending", progress=0.0)


