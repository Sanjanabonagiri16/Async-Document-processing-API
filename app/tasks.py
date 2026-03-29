import logging
import random
import time
import uuid
from datetime import datetime, timezone

import httpx

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mock_result(job_id: str, source_type: str, source_label: str | None) -> dict:
    pages = random.randint(1, 48)
    ext = (source_label or "").lower()
    doc_type = "pdf" if ext.endswith(".pdf") else "document"
    return {
        "job_id": job_id,
        "document_type": doc_type,
        "pages": pages,
        "extracted_summary": f"Mock summary for {source_label or 'uploaded file'} ({pages} pages).",
        "confidence": round(random.uniform(0.88, 0.99), 3),
        "metadata": {"source_type": source_type, "processed_version": "1.0-mock"},
    }


def _post_webhook_sync(url: str, payload: dict) -> None:
    with httpx.Client(timeout=15.0) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()


@celery_app.task(
    bind=True,
    name="app.tasks.process_document",
    autoretry_for=(RuntimeError, ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": MAX_RETRIES, "countdown": 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_document(self, job_id: str) -> None:
    jid = uuid.UUID(job_id)
    db = SessionLocal()
    try:
        job = db.get(Job, jid)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        job.status = JobStatus.processing
        job.started_at = job.started_at or _utcnow()
        job.retry_count = int(self.request.retries or 0)
        db.commit()

        delay = random.uniform(10.0, 20.0)
        logger.info("Processing job %s (simulated %.1fs)", job_id, delay)
        time.sleep(delay)

        if settings.simulate_random_failure_rate > 0 and random.random() < settings.simulate_random_failure_rate:
            raise RuntimeError("Simulated transient processing failure")

        result = _mock_result(job_id, job.source_type, job.source_label)
        job.status = JobStatus.completed
        job.completed_at = _utcnow()
        job.result = result
        job.error_message = None
        db.commit()

        if job.webhook_url:
            payload = {
                "job_id": str(job.id),
                "status": job.status.value,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "result": result,
            }
            try:
                _post_webhook_sync(job.webhook_url, payload)
                logger.info("Webhook delivered for job %s", job_id)
            except Exception as e:
                logger.warning("Webhook failed for job %s: %s", job_id, e)

    except Exception as e:
        db.rollback()
        job = db.get(Job, jid)
        retryable = isinstance(e, (RuntimeError, ConnectionError, TimeoutError))
        will_retry = retryable and int(self.request.retries or 0) < int(self.max_retries)
        if job and not will_retry:
            job.status = JobStatus.failed
            job.completed_at = _utcnow()
            job.error_message = str(e)
            db.commit()
            logger.exception("Job %s marked failed", job_id)
        raise
    finally:
        db.close()
