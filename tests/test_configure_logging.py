import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from instrukt_ai_logging import configure_logging, log_kv


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

        log_path = configure_logging(
            env_prefix="TELECLAUDE",
            app_logger_prefix="teleclaude",
            app_name="teleclaude",
        )

        logging.getLogger("teleclaude.core").debug("hello from ours")
        logging.getLogger("httpcore.http11").info("hello from third-party")

        content = _read_text(log_path)
        assert "logger=teleclaude.core" in content
        assert 'msg="hello from ours"' in content
        assert "logger=httpcore.http11" not in content


def test_spotlight_allows_selected_third_party_only(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOGGERS", "httpcore")

        log_path = configure_logging(
            env_prefix="TELECLAUDE",
            app_logger_prefix="teleclaude",
            app_name="teleclaude",
        )

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


def test_log_kv_requires_msg_key(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "WARNING")

        configure_logging(
            env_prefix="TELECLAUDE",
            app_logger_prefix="teleclaude",
            app_name="teleclaude",
        )

        with pytest.raises(ValueError):
            log_kv(logging.getLogger("teleclaude.core"), logging.INFO, {"session": "abc"})


def test_log_kv_emits_pairs(isolated_logging, monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        monkeypatch.setenv("TELECLAUDE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("TELECLAUDE_THIRD_PARTY_LOG_LEVEL", "WARNING")

        log_path = configure_logging(
            env_prefix="TELECLAUDE",
            app_logger_prefix="teleclaude",
            app_name="teleclaude",
        )

        log_kv(
            logging.getLogger("teleclaude.core"),
            logging.INFO,
            {"msg": "hello", "session": "abc123", "n": 1},
        )

        content = _read_text(log_path)
        assert 'msg="hello"' in content
        assert "session=abc123" in content
        assert "n=1" in content
