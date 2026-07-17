from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
from instrukt_ai_logging import install

_SESSION_TIMEOUT_KILL_CODE = 124  # matches the shell `timeout(1)` convention
_session_timeout_timer: threading.Timer | None = None


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "session_timeout",
        help="Hard wall-clock budget (seconds) for the whole test session; force-exits past it.",
        default="90",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    global _session_timeout_timer
    limit = float(session.config.getini("session_timeout"))
    # A per-test timeout (see [tool.pytest.ini_options] timeout) cannot catch a
    # hang outside a test body (fixture teardown, collection). This backstop
    # guarantees the whole run cannot silently sit past its budget either.
    _session_timeout_timer = threading.Timer(limit, lambda: os._exit(_SESSION_TIMEOUT_KILL_CODE))
    _session_timeout_timer.daemon = True
    _session_timeout_timer.start()


def pytest_sessionfinish() -> None:
    if _session_timeout_timer is not None:
        _session_timeout_timer.cancel()


class _FakeCompletedProcess:
    def __init__(self) -> None:
        self.returncode = 0
        self.stderr = ""
        self.stdout = ""


@pytest.fixture(autouse=True)
def _isolate_rotation_assets(  # pyright: ignore[reportUnusedFunction]
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep every test's rotation-asset writes and scheduler calls off the real machine.

    Autouse and unconditional — no test file may rely on the ambient
    environment's real HOME or XDG variables, and no test may reach a real
    scheduler/rotator binary. The scheduler subprocess seam is faked for
    every test. `test_install.py` layers tighter, still-tmp_path-rooted
    fixtures on top and re-fakes `_run_scheduler_command` explicitly for its
    failure paths.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))

    def _fake_run(args: list[str]) -> _FakeCompletedProcess:
        return _FakeCompletedProcess()

    monkeypatch.setattr(install, "_run_scheduler_command", _fake_run)
