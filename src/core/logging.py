import contextvars
import json
import logging

run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": run_id_var.get(),
        }
        return json.dumps(payload)


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
