import logging
from logging.handlers import WatchedFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from instrukt_ai_logging import InstruktAILogger, configure_logging, get_logger


@pytest.fixture()
def isolated_logging():
    previous_handlers = list(logging.root.handlers)
    previous_root_level = logging.root.level

    try:
        yield
    finally:
        for handler in logging.root.handlers:
            try:
                handler.close()
            except Exception:
                pass
        logging.root.handlers = previous_handlers
        logging.root.setLevel(previous_root_level)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_our_logs_respect_app_level_and_third_party_baseline(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "WARNING")
        monkeypatch.delenv("TELECLAUDE_THIRD_PARTY_LOGGERS", raising=False)

        log_path = configure_logging("teleclaude")

        logging.getLogger("teleclaude.core").debug("hello from ours")
        logging.getLogger("httpcore.http11").info("hello from third-party")

        content = _read_text(log_path)
        assert "logger=teleclaude.core" in content
        assert 'msg="hello from ours"' in content
        assert "logger=httpcore.http11" not in content


def test_configure_logging_uses_single_file_handler(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "WARNING")

        configure_logging("teleclaude")

        assert len(logging.root.handlers) == 1
        assert isinstance(logging.root.handlers[0], WatchedFileHandler)


def test_get_logger_returns_instrukt_logger(isolated_logging):
    logger = get_logger("teleclaude.core")
    assert isinstance(logger, InstruktAILogger)
    logger.info("hello", session="abc123", n=1)


def test_spotlight_allows_selected_third_party_only(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOGGERS", "httpcore")

        log_path = configure_logging("teleclaude")

        # Ensure records are actually created even though root is WARNING in spotlight mode.
        httpcore_logger = logging.getLogger("httpcore")
        telegram_logger = logging.getLogger("telegram")
        previous_httpcore_level = httpcore_logger.level
        previous_telegram_level = telegram_logger.level
        httpcore_logger.setLevel(logging.INFO)
        telegram_logger.setLevel(logging.INFO)

        try:
            logging.getLogger("httpcore.http11").info("httpcore info")
            logging.getLogger("telegram.ext.ExtBot").info("telegram info")
        finally:
            httpcore_logger.setLevel(previous_httpcore_level)
            telegram_logger.setLevel(previous_telegram_level)

        content = _read_text(log_path)
        assert "logger=httpcore.http11" in content
        assert 'msg="httpcore info"' in content
        assert "logger=telegram.ext.ExtBot" not in content
        assert "telegram info" not in content


def test_named_kv_logger_emits_pairs(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "WARNING")

        log_path = configure_logging("teleclaude")

        logging.getLogger("teleclaude.core").info("hello", session="abc123", n=1)

        content = _read_text(log_path)
        assert 'msg="hello"' in content
        assert "session=abc123" in content
        assert "n=1" in content


def test_muted_loggers_forced_to_warning(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("TELECLAUDE_MUTED_LOGGERS", "teleclaude.cli.tui")

        log_path = configure_logging("teleclaude")

        logging.getLogger("teleclaude.core").debug("core debug")
        logging.getLogger("teleclaude.cli.tui").debug("tui debug")
        logging.getLogger("teleclaude.cli.tui").warning("tui warning")

        content = _read_text(log_path)
        # Core debug should appear (app level is DEBUG)
        assert "logger=teleclaude.core" in content
        assert 'msg="core debug"' in content
        # Muted logger's debug should NOT appear (forced to WARNING)
        assert "tui debug" not in content
        # Muted logger's warning SHOULD appear
        assert "logger=teleclaude.cli.tui" in content
        assert 'msg="tui warning"' in content
