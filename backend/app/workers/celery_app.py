from celery import Celery
from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "loadopt",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['app.workers.tasks']
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max
    worker_prefetch_multiplier=1,
)
