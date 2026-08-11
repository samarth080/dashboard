from collections.abc import Iterator

import pytest

from src.core.logging import run_id_var


@pytest.fixture(autouse=True)
def _isolate_run_id() -> Iterator[None]:
    """Guarantee every unit test starts and ends with run_id_var at its default.

    A previous version of this cleanup ran only after a test's assertions,
    via manual `run_id_var.set(None)` calls at the bottom of each test
    function — so a failed assertion skipped the reset and leaked run_id
    state into whatever test ran next. try/finally here guarantees the
    reset always runs, pass or fail.
    """
    token = run_id_var.set(None)
    try:
        yield
    finally:
        run_id_var.reset(token)
