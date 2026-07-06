from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from instrukt_ai_logging import install

# Protocol-significant tokens for the rotation configs — named constants per
# software-development/procedure/snapshot-testing (no bare literals in content
# assertions). These are newsyslog/logrotate/launchd/systemd field identities,
# not prose.
_NEWSYSLOG_MODE = "640"
_NEWSYSLOG_COUNT = "5"
_NEWSYSLOG_SIZE_KB = "50000"
_NEWSYSLOG_WHEN = "*"
_NEWSYSLOG_COMPRESS_GLOB_FLAGS = "ZG"  # gzip-compress archives; glob-expand at rotation time
_PLIST_LABEL = "ai.instrukt.log-rotate"
_PLIST_PROGRAM = "/usr/sbin/newsyslog"
_PLIST_NO_ROOT_FLAG = "<string>-r</string>"  # newsyslog otherwise refuses to run as a non-root user
_PLIST_START_INTERVAL = "1800"
_LOGROTATE_SIZE = "size 50M"
_LOGROTATE_ROTATE = "rotate 5"
_LOGROTATE_COMPRESS = "compress"
_LOGROTATE_DELAYCOMPRESS = "delaycompress"
_LOGROTATE_MISSINGOK = "missingok"
_LOGROTATE_NOTIFEMPTY = "notifempty"
_SYSTEMD_EXEC_START_PREFIX = "ExecStart=logrotate"
_SYSTEMD_ONESHOT = "Type=oneshot"
_SYSTEMD_ON_CALENDAR = "OnCalendar=*:0/30"
_SYSTEMD_PERSISTENT = "Persistent=true"
_SYSTEMD_TIMER_UNIT = "instrukt-ai-logrotate.timer"
_PROBLEM_DAEMON_RELOAD = "daemon-reload"
_PROBLEM_WRITE_FAILURE = "could not write rotation assets"
_MAIN_LOG_ROOT_PREFIX = "log root:"
_MAIN_HEALTHY_STATUS = "status: healthy"
_MAIN_PROBLEM_PREFIX = "problem:"


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


@pytest.fixture
def rotation_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate the rotation-asset filesystem via XDG_STATE_HOME and HOME."""
    state_home = tmp_path / "state"
    home = tmp_path / "home"
    state_home.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.setenv("HOME", str(home))
    return state_home


@pytest.fixture
def successful_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Fake the scheduler subprocess boundary (launchctl/systemctl) as always succeeding."""
    calls: list[list[str]] = []

    def _fake_run(args: list[str]) -> _FakeCompletedProcess:
        calls.append(args)
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(install, "_run_scheduler_command", _fake_run)
    return calls


def test_ensure_rotation_darwin_writes_newsyslog_conf_and_plist(
    rotation_env: Path,
    successful_subprocess: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    problems = install.ensure_rotation()

    assert problems == []
    conf_content = install._newsyslog_conf_path().read_text(encoding="utf-8")
    path, mode, count, size_kb, when, flags = conf_content.split()
    assert path == f"{rotation_env / 'instrukt-ai'}/*/*.log"
    assert mode == _NEWSYSLOG_MODE
    assert count == _NEWSYSLOG_COUNT
    assert size_kb == _NEWSYSLOG_SIZE_KB
    assert when == _NEWSYSLOG_WHEN
    assert flags == _NEWSYSLOG_COMPRESS_GLOB_FLAGS

    plist_content = install._launchd_plist_path().read_text(encoding="utf-8")
    assert _PLIST_LABEL in plist_content
    assert _PLIST_PROGRAM in plist_content
    assert _PLIST_NO_ROOT_FLAG in plist_content
    assert _PLIST_START_INTERVAL in plist_content

    assert successful_subprocess == [
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(install._launchd_plist_path())]
    ]


def test_ensure_rotation_linux_writes_logrotate_conf_and_systemd_units(
    rotation_env: Path,
    successful_subprocess: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    problems = install.ensure_rotation()

    assert problems == []
    logrotate_content = install._logrotate_conf_path().read_text(encoding="utf-8")
    assert f"{rotation_env / 'instrukt-ai'}/*/*.log" in logrotate_content
    for directive in (
        _LOGROTATE_SIZE,
        _LOGROTATE_ROTATE,
        _LOGROTATE_COMPRESS,
        _LOGROTATE_DELAYCOMPRESS,
        _LOGROTATE_MISSINGOK,
        _LOGROTATE_NOTIFEMPTY,
    ):
        assert directive in logrotate_content
    assert "su " not in logrotate_content  # rotation already runs as the producing user

    service_content = install._systemd_service_path().read_text(encoding="utf-8")
    assert _SYSTEMD_EXEC_START_PREFIX in service_content
    assert _SYSTEMD_ONESHOT in service_content

    timer_content = install._systemd_timer_path().read_text(encoding="utf-8")
    assert _SYSTEMD_ON_CALENDAR in timer_content
    assert _SYSTEMD_PERSISTENT in timer_content

    assert successful_subprocess == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", _SYSTEMD_TIMER_UNIT],
    ]


def test_ensure_rotation_is_idempotent_across_runs(
    rotation_env: Path,
    successful_subprocess: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    install.ensure_rotation()
    conf_path = install._logrotate_conf_path()
    first_mtime_ns = conf_path.stat().st_mtime_ns
    first_content = conf_path.read_text(encoding="utf-8")

    install.ensure_rotation()

    assert conf_path.stat().st_mtime_ns == first_mtime_ns
    assert conf_path.read_text(encoding="utf-8") == first_content


def test_ensure_rotation_reports_problem_when_scheduler_subprocess_fails(
    rotation_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    def _fake_run(args: list[str]) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=1, stderr="no session bus")

    monkeypatch.setattr(install, "_run_scheduler_command", _fake_run)

    problems = install.ensure_rotation()

    assert problems
    assert any(_PROBLEM_DAEMON_RELOAD in problem for problem in problems)


def test_ensure_rotation_reports_problem_when_scheduler_subprocess_times_out(
    rotation_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    def _fake_run(args: list[str]) -> _FakeCompletedProcess:
        raise subprocess.TimeoutExpired(cmd=args, timeout=install._SCHEDULER_COMMAND_TIMEOUT_S)

    monkeypatch.setattr(install, "_run_scheduler_command", _fake_run)

    # An unreachable scheduler bus must be reported, never left to hang the
    # caller indefinitely.
    problems = install.ensure_rotation()

    assert problems
    assert any(_PROBLEM_DAEMON_RELOAD in problem for problem in problems)


def test_ensure_rotation_reports_problem_when_asset_write_fails(
    rotation_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    def _raise_write_error(path: Path, content: str) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(install, "_write_if_changed", _raise_write_error)

    # An unwritable rotation-asset directory must be reported, never left to
    # propagate out of ensure_rotation()'s never-raises contract.
    problems = install.ensure_rotation()

    assert problems
    assert any(_PROBLEM_WRITE_FAILURE in problem for problem in problems)


def test_ensure_rotation_tolerates_already_bootstrapped_launchd(
    rotation_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def _fake_run(args: list[str]) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=1, stderr="Service already bootstrapped")

    monkeypatch.setattr(install, "_run_scheduler_command", _fake_run)

    problems = install.ensure_rotation()

    assert problems == []


def test_main_prints_status_and_exits_zero_when_healthy(
    rotation_env: Path,
    successful_subprocess: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    install.main()

    out = capsys.readouterr().out
    assert _MAIN_LOG_ROOT_PREFIX in out
    assert _MAIN_HEALTHY_STATUS in out


def test_main_exits_non_zero_and_reports_problems(
    rotation_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    def _fake_run(args: list[str]) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=1, stderr="boom")

    monkeypatch.setattr(install, "_run_scheduler_command", _fake_run)

    with pytest.raises(SystemExit):
        install.main()

    out = capsys.readouterr().out
    assert _MAIN_PROBLEM_PREFIX in out
