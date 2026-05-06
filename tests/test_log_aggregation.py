from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from instrukt_ai_logging.logging import (
    iter_recent_log_lines_merged,
    resolve_log_files,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def app_log_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    tmp = TemporaryDirectory()
    root = Path(tmp.name)
    monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", str(root))

    app_dir = root / "demo-app"
    app_dir.mkdir(parents=True)
    yield app_dir
    tmp.cleanup()


def test_resolve_log_files_default_returns_all_log_files(app_log_dir: Path) -> None:
    _write(app_log_dir / "demo-app.log", "")
    _write(app_log_dir / "cron.log", "")
    _write(app_log_dir / "docs-watch.log", "")
    _write(app_log_dir / "demo-app.log.1", "")
    _write(app_log_dir / "demo-app.log.2.gz", "")  # excluded

    result = resolve_log_files("demo-app")
    names = sorted(p.name for p in result)
    assert names == ["cron.log", "demo-app.log", "demo-app.log.1", "docs-watch.log"]


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
        monkeypatch.setenv("INSTRUKT_AI_LOG_ROOT", tmp)
        # Directory for the app does not exist.
        assert resolve_log_files("nonexistent-app") == []


def _now_iso(offset_minutes: int = 0) -> str:
    from datetime import datetime, timezone

    dt = datetime.now(tz=timezone.utc) + timedelta(minutes=offset_minutes)
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
        f"{_now_iso(-1)} level=INFO logger=demo.daemon msg=fresh\n",
        encoding="utf-8",
    )

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=5)))
    assert len(lines) == 1
    assert "fresh" in lines[0]


def test_iter_recent_log_lines_merged_skips_files_with_mtime_before_cutoff(
    app_log_dir: Path,
) -> None:
    import os
    from datetime import datetime, timezone

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
    one_day_ago = (datetime.now(tz=timezone.utc) - timedelta(days=1)).timestamp()
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
        f"{_now_iso(-1)} level=ERROR logger=demo.daemon msg=boom\n"
        f"  Traceback (most recent call last):\n"
        f"  File 'foo.py', line 1\n"
        f"{_now_iso(0)} level=INFO logger=demo.daemon msg=after\n",
        encoding="utf-8",
    )

    files = resolve_log_files("demo-app")
    lines = list(iter_recent_log_lines_merged(files, since=timedelta(minutes=10)))
    assert len(lines) == 4
    assert "boom" in lines[0]
    assert lines[1].startswith("  Traceback")
    assert lines[2].startswith("  File")
    assert "after" in lines[3]
