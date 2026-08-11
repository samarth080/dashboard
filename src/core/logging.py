import contextvars
import json
import logging
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
    run_id_var.set(run_id)


def get_run_id() -> str | None:
    return run_id_var.get()
