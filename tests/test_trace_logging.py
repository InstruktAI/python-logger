import os
import tempfile

import pytest
from instrukt_ai_logging.logging import (
    configure_logging,
    get_logger,
)


@pytest.fixture
def clean_env():
    old_environ = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(old_environ)


def test_trace_level_logging(clean_env):
    """Verify TRACE logging works."""
    app_name = "test_trace_app"
    os.environ["TEST_TRACE_APP_LOG_LEVEL"] = "TRACE"

    # Use a temporary directory for logs
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["INSTRUKT_AI_LOG_ROOT"] = temp_dir

        log_file = configure_logging(app_name)
        logger = get_logger("test_trace_app")

        # Log at TRACE level
        logger.trace("This is a trace message", kv_key="kv_value")

        # Log at DEBUG level
        logger.debug("This is a debug message")

        # Read the log file
        with open(log_file, "r") as f:
            lines = f.readlines()

        assert len(lines) == 2

        assert "level=TRACE" in lines[0]
        assert 'msg="This is a trace message"' in lines[0]
        assert "kv_key=kv_value" in lines[0]

        assert "level=DEBUG" in lines[1]
        assert 'msg="This is a debug message"' in lines[1]


def test_trace_level_filtering(clean_env):
    """Verify TRACE logging is filtered out when level is DEBUG."""
    app_name = "test_trace_filtering"
    os.environ["TEST_TRACE_FILTERING_LOG_LEVEL"] = "DEBUG"

    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["INSTRUKT_AI_LOG_ROOT"] = temp_dir

        log_file = configure_logging(app_name)
        logger = get_logger("test_trace_filtering")

        logger.trace("This should not appear")
        logger.debug("This should appear")

        with open(log_file, "r") as f:
            lines = f.readlines()

        assert len(lines) == 1
        assert "level=DEBUG" in lines[0]
