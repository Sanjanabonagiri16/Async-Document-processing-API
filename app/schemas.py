import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class JobCreateUrl(BaseModel):
    document_url: HttpUrl
    webhook_url: HttpUrl | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    status: str
    source_type: str
    source_label: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: dict[str, Any] | None
    error_message: str | None
    retry_count: int
    webhook_url: str | None

    model_config = {"from_attributes": True}


class JobCreated(BaseModel):
    id: uuid.UUID
    status: str
    message: str = Field(default="Job accepted and queued for processing.")


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int
