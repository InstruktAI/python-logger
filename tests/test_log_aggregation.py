from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import UTC, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from instrukt_ai_logging.cli import main
from instrukt_ai_logging.logging import (
    iter_recent_log_lines_merged,
    resolve_log_files,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# Log markers shared by each fixture and its assertions — named constants per
# software-development/procedure/snapshot-testing (no bare literals in content
# assertions).
_MSG_FRESH = "fresh"
_MSG_BOOM = "boom"
_MSG_AFTER = "after"
_TRACEBACK_LINE = "  Traceback (most recent call last):"
_FILE_LINE = "  File 'foo.py', line 1"
_MSG_KEEP = "keep-me"
_MSG_GIT_NOISE = "git-noise"
_MSG_REAL_ERROR = "real-error"
_MSG_GIT_ERROR = "git-error"
_MSG_INFO = "info-line"
_MSG_CRON = "cron-line"
_MSG_DAEMON = "daemon-line"
_MSG_OLD_PREFIX = "msg=old-"
_MSG_LINE_PREFIX = "msg=line-"
_LARGE_LINE_COUNT = 20000


@pytest.fixture()
def app_log_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    tmp = TemporaryDirectory()
    root = Path(tmp.name)
    monkeypatch.setenv("XDG_STATE_HOME", str(root))

    app_dir = root / "instrukt-ai" / "demo-app"
    app_dir.mkdir(parents=True)
    yield app_dir
    tmp.cleanup()


def test_resolve_log_files_default_returns_all_log_files(app_log_dir: Path) -> None:
    _write(app_log_dir / "demo-app.log", "")
    _write(app_log_dir / "cron.log", "")
    _write(app_log_dir / "docs-watch.log", "")
    _write(app_log_dir / "demo-app.log.1", "")
    _write(app_log_dir / "demo-app.log.2.gz", "")

    result = resolve_log_files("demo-app")
    names = sorted(p.name for p in result)
    assert names == ["cron.log", "demo-app.log", "demo-app.log.1", "demo-app.log.2.gz", "docs-watch.log"]


def test_resolve_log_files_with_stems_filters_to_matching_files(app_log_dir: Path) -> None:
    _write(app_log_dir / "demo-app.log", "")
    _write(app_log_dir / "cron.log", "")
    _write(app_log_dir / "cron.log.0", "")
    _write(app_log_dir / "cron-backup.log", "")  # excluded: not matched by `cron` stem
    _write(app_log_dir / "docs-watch.log", "")

    result = resolve_log_files("demo-app", stems=["cron", "docs-watch"])
    names = sorted(p.name for p in result)
    assert names == ["cron.log", "cron.log.0", "docs-watch.log"]


def test_resolve_log_files_returns_empty_for_unknown_stem(app_log_dir: Path) -> None:
    _write(app_log_dir / "demo-app.log", "")

    assert resolve_log_files("demo-app", stems=["nope"]) == []


def test_resolve_log_files_returns_empty_when_dir_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("XDG_STATE_HOME", tmp)
        # Directory for the app does not exist.
        assert resolve_log_files("nonexistent-app") == []


def _now_iso(offset_minutes: int = 0) -> str:
    from datetime import datetime

    dt = datetime.now(tz=UTC) + timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{int(dt.microsecond / 1000):03d}Z"


def test_iter_recent_log_lines_merged_orders_by_timestamp_across_files(
    app_log_dir: Path,
) -> None:
    cron = app_log_dir / "cron.log"
    daemon = app_log_dir / "demo-app.log"

    cron.write_text(
        f"{_now_iso(-3)} level=INFO logger=demo.cron msg=cron-A\n"
        f"{_now_iso(-1)} level=INFO logger=demo.cron msg=cron-B\n",
        encoding="utf-8",
    )
    daemon.write_text(
        f"{_now_iso(-2)} level=INFO logger=demo.daemon msg=daemon-A\n"
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg=daemon-B\n",
        encoding="utf-8",
    )

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=10)))
    msgs = [line.strip().rsplit("=", 1)[-1] for line in lines]
    assert msgs == ["cron-A", "daemon-A", "cron-B", "daemon-B"]


def test_iter_recent_log_lines_merged_respects_since_cutoff(app_log_dir: Path) -> None:
    daemon = app_log_dir / "demo-app.log"
    daemon.write_text(
        f"{_now_iso(-30)} level=INFO logger=demo.daemon msg=old\n"
        f"{_now_iso(-1)} level=INFO logger=demo.daemon msg={_MSG_FRESH}\n",
        encoding="utf-8",
    )

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=5)))
    assert len(lines) == 1
    assert _MSG_FRESH in lines[0]


def test_iter_recent_log_lines_merged_skips_files_with_mtime_before_cutoff(
    app_log_dir: Path,
) -> None:
    import os
    from datetime import datetime

    fresh = app_log_dir / "demo-app.log"
    fresh.write_text(
        f"{_now_iso(-1)} level=INFO logger=demo.daemon msg=fresh\n",
        encoding="utf-8",
    )
    stale = app_log_dir / "stale.log"
    stale.write_text(
        f"{_now_iso(-1)} level=INFO logger=stale msg=stale-but-line-looks-recent\n",
        encoding="utf-8",
    )
    # Force stale.log's mtime to 1 day ago — older than --since=10m cutoff.
    one_day_ago = (datetime.now(tz=UTC) - timedelta(days=1)).timestamp()
    os.utime(stale, (one_day_ago, one_day_ago))

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=10)))
    msgs = [line.strip().rsplit("=", 1)[-1] for line in lines]
    assert msgs == ["fresh"]


def test_iter_recent_log_lines_merged_keeps_continuation_lines_with_parent(
    app_log_dir: Path,
) -> None:
    daemon = app_log_dir / "demo-app.log"
    daemon.write_text(
        f"{_now_iso(-1)} level=ERROR logger=demo.daemon msg={_MSG_BOOM}\n"
        f"{_TRACEBACK_LINE}\n"
        f"{_FILE_LINE}\n"
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg={_MSG_AFTER}\n",
        encoding="utf-8",
    )

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=10)))
    assert len(lines) == 4
    assert _MSG_BOOM in lines[0]
    assert lines[1].startswith(_TRACEBACK_LINE)
    assert lines[2].startswith(_FILE_LINE)
    assert _MSG_AFTER in lines[3]


def test_iter_recent_log_lines_merged_reads_tail_window_of_large_file(
    app_log_dir: Path,
) -> None:
    # A large body of old lines (well past the 256 KiB backward probe) followed by
    # a recent window that includes a multi-line entry. The reader must return only
    # the recent lines — proving it locates the window near EOF rather than scanning
    # the whole file — and must keep the continuation line with its parent across
    # the seek boundary.
    daemon = app_log_dir / "demo-app.log"
    old_block = "".join(
        f"{_now_iso(-30)} level=INFO logger=demo.daemon {_MSG_OLD_PREFIX}{i}\n" for i in range(_LARGE_LINE_COUNT)
    )
    recent_block = (
        f"{_now_iso(-1)} level=ERROR logger=demo.daemon msg={_MSG_BOOM}\n"
        f"{_TRACEBACK_LINE}\n"
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg={_MSG_AFTER}\n"
    )
    daemon.write_text(old_block + recent_block, encoding="utf-8")
    assert daemon.stat().st_size > 262144  # forces the backward-probe path (offset > 0)

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=5)))
    assert len(lines) == 3
    assert _MSG_BOOM in lines[0]
    assert lines[1].startswith(_TRACEBACK_LINE)
    assert _MSG_AFTER in lines[2]
    assert all(_MSG_OLD_PREFIX not in line for line in lines)


def test_iter_recent_log_lines_merged_returns_whole_large_file_within_window(
    app_log_dir: Path,
) -> None:
    # Every line is inside the window but the file exceeds one probe: the backward
    # probe must grow to the file start (offset 0) and return all lines, not just
    # the final probe's worth.
    daemon = app_log_dir / "demo-app.log"
    daemon.write_text(
        "".join(
            f"{_now_iso(-1)} level=INFO logger=demo.daemon {_MSG_LINE_PREFIX}{i}\n" for i in range(_LARGE_LINE_COUNT)
        ),
        encoding="utf-8",
    )
    assert daemon.stat().st_size > 262144

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=5)))
    assert len(lines) == _LARGE_LINE_COUNT
    first_marker = f"{_MSG_LINE_PREFIX}0"
    last_marker = f"{_MSG_LINE_PREFIX}{_LARGE_LINE_COUNT - 1}"
    assert first_marker in lines[0]
    assert last_marker in lines[-1]


def test_cli_exclude_drops_matching_lines(
    app_log_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    daemon = app_log_dir / "demo-app.log"
    daemon.write_text(
        f"{_now_iso(-1)} level=ERROR logger=demo.git.exec msg={_MSG_GIT_NOISE}\n"
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg={_MSG_KEEP}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["instrukt-ai-logs", "demo-app", "--exclude", r"logger=demo\.git\.exec"])
    main()

    out = capsys.readouterr().out
    assert _MSG_KEEP in out
    assert _MSG_GIT_NOISE not in out


def test_cli_exclude_applies_after_grep(
    app_log_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    daemon = app_log_dir / "demo-app.log"
    daemon.write_text(
        f"{_now_iso(-2)} level=ERROR logger=demo.git.exec msg={_MSG_GIT_ERROR}\n"
        f"{_now_iso(-1)} level=ERROR logger=demo.daemon msg={_MSG_REAL_ERROR}\n"
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg={_MSG_INFO}\n",
        encoding="utf-8",
    )

    # Keep only ERROR lines, then drop the git seam ones.
    monkeypatch.setattr(
        sys,
        "argv",
        ["instrukt-ai-logs", "demo-app", "--grep", "level=ERROR", "--exclude", r"logger=demo\.git\.exec"],
    )
    main()

    out = capsys.readouterr().out
    assert _MSG_REAL_ERROR in out
    assert _MSG_GIT_ERROR not in out
    assert _MSG_INFO not in out


def test_cli_include_alias_matches_logs_flag(
    app_log_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (app_log_dir / "demo-app.log").write_text(
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg={_MSG_DAEMON}\n", encoding="utf-8"
    )
    (app_log_dir / "cron.log").write_text(
        f"{_now_iso(0)} level=INFO logger=demo.cron msg={_MSG_CRON}\n", encoding="utf-8"
    )

    monkeypatch.setattr(sys, "argv", ["instrukt-ai-logs", "demo-app", "--include", "cron"])
    main()

    out = capsys.readouterr().out
    assert _MSG_CRON in out
    assert _MSG_DAEMON not in out
