"""Structured JSON logging with run_id correlation across async/task boundaries.

`run_id_var` is a ContextVar rather than a global so concurrent requests and
task executions (which may interleave on the same event loop) each see their
own run_id. Prefer `run_context` to set it: it restores whatever value
preceded it on exit, so a run_id scoped to one request or task can never leak
into the next. `set_run_id` is a lower-level escape hatch for callback-style
integrations (e.g. Celery's `task_prerun` signal) that hand you no scope to
wrap with a context manager.
"""

import contextvars
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)

# Attribute names present on every LogRecord regardless of what the caller
# logs. Computed from a real record (rather than hand-maintained) so it
# stays correct across Python versions that add fields (e.g. 3.12's
# `taskName`). Anything in record.__dict__ beyond this set came from
# `extra={...}` and should be merged into the JSON payload.
_STANDARD_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": run_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_ATTRS
        }
        payload.update(extra)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def set_run_id(run_id: str) -> None:
    """Set run_id for the rest of this context, with no way to restore the previous value.

    Use only where there is no enclosing scope to wrap with `run_context` —
    e.g. a Celery `task_prerun` signal handler, which fires as a bare
    callback with nothing to `with`. Everywhere else, prefer `run_context`.
    """
    run_id_var.set(run_id)


def get_run_id() -> str | None:
    return run_id_var.get()


@contextmanager
def run_context(run_id: str) -> Iterator[str]:
    """Scope run_id to the wrapped block, restoring the previous value on exit.

    Preferred over `set_run_id` wherever there is a well-defined unit of work
    (a request handler, a task body, a test): it guarantees a run_id set for
    one unit of work cannot leak into whatever runs next in the same context,
    even if the block raises.
    """
    token = run_id_var.set(run_id)
    try:
        yield run_id
    finally:
        run_id_var.reset(token)
