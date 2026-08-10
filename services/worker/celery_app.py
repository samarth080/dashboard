import uuid

from celery import Celery
from celery.signals import task_prerun

from src.core.logging import configure_logging, set_run_id
from src.core.settings import get_settings

settings = get_settings()

# `include` tells Celery which task modules to import at worker startup. The
# worker process is launched as `-A services.worker.celery_app`, which only
# imports this module; without `include`, tasks.py's `@celery_app.task`
# decorator never runs in that process, so the worker never registers `ping`
# and every task dispatch fails with `celery.exceptions.NotRegistered`.
celery_app = Celery(
    "engine_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["services.worker.tasks"],
)

configure_logging()


@task_prerun.connect
def bind_run_id(*args, **kwargs) -> None:
    """Give every task execution its own run_id so worker logs are traceable."""
    set_run_id(str(uuid.uuid4()))
