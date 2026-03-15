from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import traceback
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import AuditJob, AuditResult, Document, Strategy
from app.schemas import AuditResultPayload, ReviewPlan
from app.services.heuristic_auditor import normalize_model_results, run_heuristic_audit
from app.services.kimi_client import KimiClient
from app.services.pdf_service import (
    analyze_document,
    ensure_document_path,
    get_page_text_blocks,
    read_page_index,
    write_page_index,
)
from app.services.planning_service import build_review_plan

logger = logging.getLogger(__name__)


class AuditWorker:
    def __init__(self, session_factory: sessionmaker[Session], settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._queue: queue.Queue[str] = queue.Queue()
        self._shutdown_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="audit-worker", daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()
        logger.info("Audit worker thread started.")

    def stop(self) -> None:
        if not self._started:
            return
        self._shutdown_event.set()
        self._queue.put("__STOP__")
        self._thread.join(timeout=5.0)
        self._started = False
        logger.info("Audit worker thread stopped.")

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)
        logger.info("Audit job queued. job_id=%s queue_size=%s", job_id, self._queue.qsize())

    def _run(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if job_id == "__STOP__":
                self._queue.task_done()
                break
            try:
                logger.info("Audit worker picked job. job_id=%s", job_id)
                self._process_job(job_id)
            finally:
                self._queue.task_done()

    def _set_job_state(
        self,
        db: Session,
        job: AuditJob,
        status: str | None = None,
        progress: float | None = None,
        error_message: str | None = None,
    ) -> None:
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if error_message is not None:
            job.error_message = error_message
        db.add(job)
        db.commit()
        db.refresh(job)

    def _process_job(self, job_id: str) -> None:
        with self._session_factory() as db:
            job = db.get(AuditJob, job_id)
            if job is None:
                logger.warning("Audit job not found when processing. job_id=%s", job_id)
                return
            try:
                logger.info("Audit job processing started. job_id=%s", job_id)
                self._set_job_state(db, job, status="running", progress=5.0, error_message=None)

                doc = db.get(Document, job.doc_id)
                strategy = db.scalar(select(Strategy).where(Strategy.id == job.strategy_id))
                if doc is None or strategy is None:
                    raise RuntimeError("Document or strategy not found.")
                logger.info(
                    "Loaded audit context. job_id=%s doc_id=%s strategy_id=%s",
                    job_id,
                    job.doc_id,
                    job.strategy_id,
                )
                _ = strategy.rules
                document_path = ensure_document_path(doc.path)

                page_index = read_page_index(doc.id)
                if not page_index:
                    logger.info("Page index cache miss. job_id=%s doc_id=%s", job_id, doc.id)
                    page_count, doc_type, page_index = analyze_document(
                        document_path,
                        max_preview_chars=self._settings.max_preview_chars,
                    )
                    doc.page_count = page_count
                    doc.doc_type = doc_type
                    db.add(doc)
                    db.commit()
                    write_page_index(doc.id, page_index)
                    logger.info("Page index generated during audit. job_id=%s page_count=%s doc_type=%s", job_id, page_count, doc_type)

                review_plan = build_review_plan(
                    rules=strategy.rules,
                    pages=page_index,
                    doc_type=doc.doc_type,
                    max_page_budget=self._settings.max_page_budget,
                    budget_ratio=self._settings.max_page_budget_ratio,
                    min_review_pages=self._settings.min_review_pages,
                )
                job.review_plan_json = review_plan.model_dump_json()
                self._set_job_state(db, job, progress=20.0)
                logger.info(
                    "Review plan built. job_id=%s selected_pages=%s",
                    job_id,
                    [item.page for item in review_plan.selected_pages],
                )

                page_blocks: dict[int, Any] = {}
                page_payload: list[dict[str, Any]] = []
                selected_pages = [item.page for item in review_plan.selected_pages]
                for idx, selected in enumerate(review_plan.selected_pages, start=1):
                    text_blocks = []
                    if selected.depth in {"text_blocks", "both"}:
                        text_blocks = get_page_text_blocks(document_path, selected.page)
                    page_blocks[selected.page] = text_blocks
                    page_payload.append(
                        {
                            "page_number": selected.page,
                            "depth": selected.depth,
                            "reason": selected.reason,
                            "text_blocks": [block.model_dump() for block in text_blocks[:60]],
                        }
                    )
                    step = 20.0 + (idx / max(len(review_plan.selected_pages), 1)) * 35.0
                    self._set_job_state(db, job, progress=min(step, 60.0))
                logger.info("Collected page payload. job_id=%s page_payload_count=%s", job_id, len(page_payload))

                strategy_payload = {
                    "strategy_id": strategy.id,
                    "strategy_name": strategy.name,
                    "rules": [
                        {
                            "rule_id": rule.id,
                            "title": rule.title,
                            "description": rule.description,
                            "severity": rule.severity,
                            "is_required": rule.is_required,
                        }
                        for rule in strategy.rules
                    ],
                }

                kimi = KimiClient(self._settings)
                audit_logs: list[str] = []
                audit_results: list[AuditResultPayload]

                if kimi.enabled and page_payload:
                    try:
                        raw_results, model_logs = asyncio.run(
                            kimi.audit(
                                strategy_payload=strategy_payload,
                                review_plan=review_plan,
                                page_payload=page_payload,
                            )
                        )
                        audit_results = normalize_model_results(raw_results)
                        audit_logs.extend(model_logs)
                        logger.info("LLM audit succeeded. job_id=%s result_count=%s", job_id, len(audit_results))
                    except Exception as exc:  # pragma: no cover - fallback path is tested instead
                        audit_logs.append(f"LLM audit failed, fallback activated: {exc}")
                        logger.exception("LLM audit failed, using heuristic fallback. job_id=%s", job_id)
                        audit_results, heuristic_logs = run_heuristic_audit(
                            rules=strategy.rules,
                            review_plan=review_plan,
                            page_blocks=page_blocks,
                        )
                        audit_logs.extend(heuristic_logs)
                else:
                    audit_results, heuristic_logs = run_heuristic_audit(
                        rules=strategy.rules,
                        review_plan=review_plan,
                        page_blocks=page_blocks,
                    )
                    audit_logs.extend(heuristic_logs)
                    logger.info("Using heuristic audit path. job_id=%s result_count=%s", job_id, len(audit_results))

                db.execute(delete(AuditResult).where(AuditResult.job_id == job.id))
                for result in audit_results:
                    db.add(
                        AuditResult(
                            job_id=job.id,
                            doc_id=doc.id,
                            rule_id=result.rule_id,
                            page=result.page,
                            bbox=json.dumps(result.bbox, ensure_ascii=False),
                            content=result.content,
                            suggestion=result.suggestion,
                            status=result.status,
                            severity=result.severity,
                        )
                    )
                db.commit()
                logger.info("Audit results persisted. job_id=%s result_count=%s", job_id, len(audit_results))

                job.visited_pages_json = json.dumps(selected_pages, ensure_ascii=False)
                job.audit_log = json.dumps(audit_logs, ensure_ascii=False)
                job.review_plan_json = review_plan.model_dump_json()
                self._set_job_state(db, job, status="completed", progress=100.0, error_message=None)
                logger.info("Audit job completed. job_id=%s", job_id)
            except Exception as exc:
                error_text = f"{exc}\n{traceback.format_exc()}"
                self._set_job_state(db, job, status="failed", progress=100.0, error_message=error_text)
                logger.exception("Audit job failed. job_id=%s", job_id)


