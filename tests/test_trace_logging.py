import os
import tempfile

import pytest
from instrukt_ai_logging.logging import (
    configure_logging,
    get_logger,
)

# Log markers shared by each test and its assertions — named constants per
# software-development/procedure/snapshot-testing (no bare literals in content
# assertions). The logfmt field fragments are derived from the markers so the
# expected output stays in sync with what is logged.
_TRACE_MSG = "This is a trace message"
_DEBUG_MSG = "This is a debug message"
_KV_KEY = "kv_key"
_KV_VALUE = "kv_value"
_FILTERED_TRACE_MSG = "This should not appear"
_FILTERED_DEBUG_MSG = "This should appear"

_LEVEL_TRACE_FIELD = "level=TRACE"
_LEVEL_DEBUG_FIELD = "level=DEBUG"
_TRACE_MSG_FIELD = f'msg="{_TRACE_MSG}"'
_DEBUG_MSG_FIELD = f'msg="{_DEBUG_MSG}"'
_KV_FIELD = f"{_KV_KEY}={_KV_VALUE}"


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
        logger.trace(_TRACE_MSG, **{_KV_KEY: _KV_VALUE})

        # Log at DEBUG level
        logger.debug(_DEBUG_MSG)

        # Read the log file
        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 2

        assert _LEVEL_TRACE_FIELD in lines[0]
        assert _TRACE_MSG_FIELD in lines[0]
        assert _KV_FIELD in lines[0]

        assert _LEVEL_DEBUG_FIELD in lines[1]
        assert _DEBUG_MSG_FIELD in lines[1]


def test_trace_level_filtering(clean_env):
    """Verify TRACE logging is filtered out when level is DEBUG."""
    app_name = "test_trace_filtering"
    os.environ["TEST_TRACE_FILTERING_LOG_LEVEL"] = "DEBUG"

    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["INSTRUKT_AI_LOG_ROOT"] = temp_dir

        log_file = configure_logging(app_name)
        logger = get_logger("test_trace_filtering")

        logger.trace(_FILTERED_TRACE_MSG)
        logger.debug(_FILTERED_DEBUG_MSG)

        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 1
        assert _LEVEL_DEBUG_FIELD in lines[0]
