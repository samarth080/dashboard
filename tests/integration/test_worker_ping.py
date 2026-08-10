import subprocess
import time

import pytest

from services.worker.celery_app import celery_app
from services.worker.tasks import ping


@pytest.fixture(scope="module")
def celery_worker_process():
    proc = subprocess.Popen(
        [
            "uv", "run", "celery", "-A", "services.worker.celery_app", "worker",
            "--loglevel=info", "--pool=solo",
        ]
    )
    for _ in range(30):
        if celery_app.control.ping(timeout=1):
            break
        time.sleep(1)
    else:
        proc.terminate()
        raise RuntimeError("celery worker did not start in time")
    yield proc
    proc.terminate()
    proc.wait(timeout=10)


def test_ping_task_round_trips_through_redis(celery_worker_process):
    async_result = ping.delay()
    assert async_result.get(timeout=10) == "pong"
