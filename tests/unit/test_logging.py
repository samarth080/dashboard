import json
import logging
import sys
from datetime import UTC, datetime

import pytest

from src.core.logging import JSONFormatter, get_run_id, run_context, set_run_id


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


def test_json_formatter_run_id_is_none_by_default():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="no run", args=(), exc_info=None,
    )
    payload = json.loads(JSONFormatter().format(record))
    assert payload["run_id"] is None


def test_json_formatter_includes_a_parseable_timestamp():
    """FIX 4: no timestamp field at all means events can't be ordered or correlated."""
    before = datetime.now(UTC)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    after = datetime.now(UTC)

    payload = json.loads(JSONFormatter().format(record))
    assert "timestamp" in payload
    parsed = datetime.fromisoformat(payload["timestamp"])
    assert before <= parsed <= after


def test_json_formatter_includes_traceback_on_exception():
    """FIX 4: exc_info was never serialized, so logger.exception() silently
    discarded the stack trace — undebuggable in production.
    """
    logger = logging.getLogger("test_exception_logger")
    try:
        raise ValueError("boom")
    except ValueError:
        record = logger.makeRecord(
            logger.name, logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    payload = json.loads(JSONFormatter().format(record))
    assert "exception" in payload
    assert "ValueError: boom" in payload["exception"]
    assert "Traceback" in payload["exception"]


def test_json_formatter_merges_extra_fields():
    """FIX 4: extra={...} was dropped, defeating the point of JSON logging."""
    logger = logging.getLogger("test_extra_logger")
    record = logger.makeRecord(
        logger.name, logging.INFO, __file__, 1, "job finished", (), None,
        extra={"job_id": 7},
    )
    payload = json.loads(JSONFormatter().format(record))
    assert payload["job_id"] == 7


def test_run_context_sets_and_restores_run_id():
    """FIX 5 regression test.

    ContextVar.set() returns a Token needed to restore the previous value;
    the old set_run_id() threw it away, so a run_id set for one unit of
    work could never be restored and leaked into whatever ran next in the
    same context.
    """
    assert get_run_id() is None
    with run_context("outer") as yielded:
        assert yielded == "outer"
        assert get_run_id() == "outer"
    assert get_run_id() is None


def test_run_context_nesting_restores_the_outer_value():
    with run_context("outer"):
        assert get_run_id() == "outer"
        with run_context("inner"):
            assert get_run_id() == "inner"
        assert get_run_id() == "outer"
    assert get_run_id() is None


def test_run_context_restores_previous_value_even_if_the_block_raises():
    with run_context("outer"):
        with pytest.raises(RuntimeError), run_context("inner"):
            raise RuntimeError("boom")
        assert get_run_id() == "outer"
