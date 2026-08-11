from services.worker.celery_app import bind_run_id
from src.core.logging import get_run_id


def test_task_prerun_handler_sets_a_run_id():
    assert get_run_id() is None

    bind_run_id()

    first = get_run_id()
    assert first is not None

    bind_run_id()
    assert get_run_id() != first  # each task execution gets a fresh id
