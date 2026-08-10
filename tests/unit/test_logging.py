import json
import logging

from src.core.logging import JSONFormatter, run_id_var, set_run_id


def test_json_formatter_includes_run_id_and_message():
    set_run_id("abc-123")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    formatted = JSONFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["run_id"] == "abc-123"
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    run_id_var.set(None)


def test_json_formatter_run_id_is_none_by_default():
    run_id_var.set(None)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="no run", args=(), exc_info=None,
    )
    payload = json.loads(JSONFormatter().format(record))
    assert payload["run_id"] is None
