"""Ensure user-space log rotation assets for InstruktAI logs.

Rotation runs entirely as the producing user: a per-user rotation conf plus a
per-user scheduler (launchd LaunchAgent on macOS, systemd user timer on
Linux). No `/etc` configuration, no sudo, no system rotation daemon ever
touches these files, so root-owned recreated logs are structurally
unexpressible.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_NEWSYSLOG_BIN = "/usr/sbin/newsyslog"
_LAUNCHD_LABEL = "ai.instrukt.log-rotate"
_SYSTEMD_UNIT_NAME = "instrukt-ai-logrotate"


def _state_home_root() -> Path:
    """Resolve `$XDG_STATE_HOME/instrukt-ai` (fallback `~/.local/state`)."""
    xdg_state_home = os.getenv("XDG_STATE_HOME")
    state_home = Path(xdg_state_home).expanduser() if xdg_state_home else Path("~/.local/state").expanduser()
    return state_home / "instrukt-ai"


def _config_dir() -> Path:
    return Path.home() / ".config" / "instrukt-ai"


def _newsyslog_conf_path() -> Path:
    return _config_dir() / "newsyslog.conf"


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCHD_LABEL}.plist"


def _logrotate_conf_path() -> Path:
    return _config_dir() / "logrotate.conf"


def _systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _systemd_service_path() -> Path:
    return _systemd_user_dir() / f"{_SYSTEMD_UNIT_NAME}.service"


def _systemd_timer_path() -> Path:
    return _systemd_user_dir() / f"{_SYSTEMD_UNIT_NAME}.timer"


def _newsyslog_conf(log_root: Path) -> str:
    """One glob line: 5 gzipped archives at 50 MB, evaluated at rotation time (G flag)."""
    return f"{log_root}/*/*.log  640  5  50000  *  ZG\n"


def _launchd_plist(conf_path: Path) -> str:
    # newsyslog refuses to run at all unless invoked as root or with -r; our
    # conf lines carry no pid/signal field, so -r's "won't HUP syslogd" caveat
    # doesn't apply here.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{_NEWSYSLOG_BIN}</string>
        <string>-r</string>
        <string>-f</string>
        <string>{conf_path}</string>
    </array>
    <key>StartInterval</key>
    <integer>1800</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""


def _logrotate_conf(log_root: Path) -> str:
    """Default move+create rotation; WatchedFileHandler reopens on inode change."""
    return f"""{log_root}/*/*.log {{
    size 50M
    rotate 5
    compress
    delaycompress
    missingok
    notifempty
}}
"""


def _systemd_service(conf_path: Path, state_file: Path) -> str:
    return f"""[Unit]
Description=InstruktAI log rotation

[Service]
Type=oneshot
ExecStart=logrotate --state {state_file} {conf_path}
"""


def _systemd_timer() -> str:
    return """[Unit]
Description=InstruktAI log rotation timer

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
"""


def _write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_SCHEDULER_COMMAND_TIMEOUT_S = 10.0


def _run_scheduler_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    # No Python API wraps launchd's per-user service bus or the systemd user
    # D-Bus/session manager; shell out to launchctl/systemctl. Routed through
    # this wrapper (rather than calling subprocess.run directly) so tests can
    # fake just this boundary without patching the shared subprocess module.
    # A bounded timeout and closed stdin keep an unreachable service bus (no
    # GUI/user session, e.g. a headless CI runner) from hanging the caller
    # forever instead of failing fast.
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=_SCHEDULER_COMMAND_TIMEOUT_S,
    )


def _ensure_launchd_loaded(plist_path: Path) -> list[str]:
    uid = os.getuid()
    try:
        result = _run_scheduler_command(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"launchctl bootstrap failed to run: {exc}"]

    if result.returncode == 0 or "already bootstrapped" in result.stderr.lower():
        return []

    # macOS reports EIO(5), not "already bootstrapped", when re-bootstrapping an already-loaded agent.
    # Confirm with `print` exit status; a nonzero result preserves the original bootstrap failure.
    try:
        loaded_result = _run_scheduler_command(["launchctl", "print", f"gui/{uid}/{_LAUNCHD_LABEL}"])
    except (OSError, subprocess.TimeoutExpired):
        return [f"launchctl bootstrap failed: {result.stderr.strip()}"]

    if loaded_result.returncode == 0:
        return []
    return [f"launchctl bootstrap failed: {result.stderr.strip()}"]


def _ensure_systemd_loaded() -> list[str]:
    try:
        reload_result = _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"systemctl daemon-reload failed to run: {exc}"]

    if reload_result.returncode != 0:
        return [f"systemctl daemon-reload failed: {reload_result.stderr.strip()}"]

    try:
        enable_result = _run_scheduler_command(
            ["systemctl", "--user", "enable", "--now", f"{_SYSTEMD_UNIT_NAME}.timer"]
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"systemctl enable failed to run: {exc}"]

    if enable_result.returncode != 0:
        return [f"systemctl enable failed: {enable_result.stderr.strip()}"]
    return []


def ensure_rotation() -> list[str]:
    """Idempotently ensure user-space rotation assets exist and are scheduled.

    Never raises. Returns human-readable problem strings for anything that
    could not be resolved; an empty list means rotation is healthy.
    """
    log_root = _state_home_root()

    if sys.platform == "darwin":
        conf_path = _newsyslog_conf_path()
        plist_path = _launchd_plist_path()
        try:
            _write_if_changed(conf_path, _newsyslog_conf(log_root))
            _write_if_changed(plist_path, _launchd_plist(conf_path))
        except OSError as exc:
            return [f"could not write rotation assets: {exc}"]
        return _ensure_launchd_loaded(plist_path)

    conf_path = _logrotate_conf_path()
    service_path = _systemd_service_path()
    timer_path = _systemd_timer_path()
    state_file = log_root / "logrotate.state"
    try:
        _write_if_changed(conf_path, _logrotate_conf(log_root))
        _write_if_changed(service_path, _systemd_service(conf_path, state_file))
        _write_if_changed(timer_path, _systemd_timer())
    except OSError as exc:
        return [f"could not write rotation assets: {exc}"]
    return _ensure_systemd_loaded()


def main() -> None:
    log_root = _state_home_root()
    sys.stdout.write(f"log root: {log_root}\n")
    sys.stdout.write(
        f"rotation conf: {_newsyslog_conf_path() if sys.platform == 'darwin' else _logrotate_conf_path()}\n"
    )
    sys.stdout.write(f"scheduler: {_launchd_plist_path() if sys.platform == 'darwin' else _systemd_timer_path()}\n")

    problems = ensure_rotation()
    if problems:
        for problem in problems:
            sys.stdout.write(f"problem: {problem}\n")
        raise SystemExit(1)
    sys.stdout.write("status: healthy\n")


if __name__ == "__main__":
    main()
