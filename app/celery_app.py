from celery import Celery
from celery.signals import worker_ready

from app.config import settings

celery_app = Celery(
    "doc_processor",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@worker_ready.connect
def _create_tables_on_worker_start(sender=None, **kwargs) -> None:
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
