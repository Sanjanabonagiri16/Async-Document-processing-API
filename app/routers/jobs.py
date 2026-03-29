import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus
from app.rate_limit import limiter
from app.schemas import JobCreated, JobCreateUrl, JobListResponse, JobResponse
from app.tasks import process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def _enqueue(job: Job) -> None:
    process_document.delay(str(job.id))
    logger.info("Enqueued job %s", job.id)


@router.post("", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.api_rate_limit)
def create_job_from_url(
    request: Request,
    payload: JobCreateUrl,
    db: Session = Depends(get_db),
) -> JobCreated:
    """Create a job from a document URL (JSON body). Swagger shows an editable request body here."""
    job = Job(
        status=JobStatus.queued,
        source_type="url",
        source_label=str(payload.document_url),
        webhook_url=str(payload.webhook_url) if payload.webhook_url else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _enqueue(job)
    return JobCreated(id=job.id, status=job.status.value)


@router.post("/upload", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.api_rate_limit)
async def create_job_from_upload(
    request: Request,
    file: Annotated[UploadFile, File(description="Document file to process")],
    webhook_url: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
) -> JobCreated:
    """Create a job from an uploaded file (multipart). Use this in Swagger for file pickers."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a filename.")
    job = Job(
        status=JobStatus.queued,
        source_type="upload",
        source_label=file.filename,
        webhook_url=webhook_url.strip() if webhook_url else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _enqueue(job)
    return JobCreated(id=job.id, status=job.status.value)


@router.get("", response_model=JobListResponse)
@limiter.limit(settings.read_rate_limit)
def list_jobs(
    request: Request,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> JobListResponse:
    q = select(Job)
    count_q = select(func.count()).select_from(Job)
    if status_filter:
        try:
            st = JobStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Use one of: {[s.value for s in JobStatus]}.",
            )
        q = q.where(Job.status == st)
        count_q = count_q.where(Job.status == st)
    total = db.scalar(count_q) or 0
    q = q.order_by(Job.created_at.desc()).offset(offset).limit(limit)
    rows = list(db.scalars(q).all())
    return JobListResponse(
        items=[JobResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
@limiter.limit(settings.read_rate_limit)
def get_job(request: Request, job_id: uuid.UUID, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job
