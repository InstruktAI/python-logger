from __future__ import annotations

import gzip
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from instrukt_ai_logging.cli import main
from syrupy.assertion import SnapshotAssertion

_LOG_ROOT_PLACEHOLDER = "<LOG_ROOT>"
_NEWEST_TS_PLACEHOLDER = "<NEWEST_TS>"

_MSG_ARCHIVED = "archived-line"
_MSG_LIVE_EARLY = "live-early"
_MSG_LIVE_LATE = "live-late"
_MSG_STALE_ARCHIVE = "stale-archive"
_MSG_RECENTLY_TOUCHED = "recently-touched-stale-content"
_MSG_TRUE_NEWEST = "older-mtime-newest-content"


@pytest.fixture()
def app_log_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    tmp = TemporaryDirectory()
    root = Path(tmp.name)
    monkeypatch.setenv("XDG_STATE_HOME", str(root))

    app_dir = root / "instrukt-ai" / "demo-app"
    app_dir.mkdir(parents=True)
    yield app_dir
    tmp.cleanup()


def _now_iso(offset_minutes: int = 0) -> str:
    dt = datetime.now(tz=UTC) + timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{int(dt.microsecond / 1000):03d}Z"


def _message(line: str) -> str:
    return line.strip().rsplit("=", 1)[-1]


@pytest.mark.spec("project/spec/feature/log_reading/time-window", "UC-TW1")
@pytest.mark.functional
def test_since_returns_in_window_lines_from_rotated_gzip_archive(
    app_log_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    live = app_log_dir / "demo-app.log"
    live.write_text(
        f"{_now_iso(-4)} level=INFO logger=demo.daemon msg={_MSG_LIVE_EARLY}\n"
        f"{_now_iso(-1)} level=INFO logger=demo.daemon msg={_MSG_LIVE_LATE}\n",
        encoding="utf-8",
    )

    archive = app_log_dir / "demo-app.log.1.gz"
    with gzip.open(archive, "wt", encoding="utf-8") as f:
        f.write(f"{_now_iso(-2)} level=INFO logger=demo.daemon msg={_MSG_ARCHIVED}\n")

    stale_archive = app_log_dir / "demo-app.log.2.gz"
    with gzip.open(stale_archive, "wt", encoding="utf-8") as f:
        f.write(f"{_now_iso(-60)} level=INFO logger=demo.daemon msg={_MSG_STALE_ARCHIVE}\n")
    one_hour_ago = (datetime.now(tz=UTC) - timedelta(hours=1)).timestamp()
    os.utime(stale_archive, (one_hour_ago, one_hour_ago))

    monkeypatch.setattr(sys, "argv", ["instrukt-ai-logs", "demo-app", "--since", "10m"])
    main()

    lines = capsys.readouterr().out.splitlines()
    assert [_message(line) for line in lines] == [_MSG_LIVE_EARLY, _MSG_ARCHIVED, _MSG_LIVE_LATE]


@pytest.mark.spec("project/spec/feature/log_reading/time-window", "UC-TW2")
@pytest.mark.functional
def test_since_discloses_root_and_newest_entry_when_result_is_empty(
    app_log_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    # Recently-touched stem whose own content is the older of the two — a probe
    # that simply trusts "newest mtime" would report this file's timestamp.
    recently_touched = app_log_dir / "stem-touched.log"
    recently_touched.write_text(
        f"{_now_iso(-90)} level=INFO logger=demo.daemon msg={_MSG_RECENTLY_TOUCHED}\n",
        encoding="utf-8",
    )
    now = datetime.now(tz=UTC).timestamp()
    os.utime(recently_touched, (now, now))

    # Second stem: older mtime than the file above, but its content is the true
    # root-wide newest entry.
    true_newest = app_log_dir / "stem-newest.log"
    true_newest_ts = _now_iso(-70)
    true_newest.write_text(
        f"{true_newest_ts} level=INFO logger=demo.daemon msg={_MSG_TRUE_NEWEST}\n",
        encoding="utf-8",
    )
    older_mtime = (datetime.now(tz=UTC) - timedelta(minutes=60)).timestamp()
    os.utime(true_newest, (older_mtime, older_mtime))

    monkeypatch.setattr(sys, "argv", ["instrukt-ai-logs", "demo-app", "--since", "10m"])
    main()

    captured = capsys.readouterr()
    assert not captured.out

    # The directory and timestamp are nondeterministic per run (a fresh tmp dir,
    # a clock-relative offset); redact them to fixture-owned placeholders before
    # snapshotting so the snapshot pins the message's structure and the fact that
    # both values are present, not their per-run values.
    normalized_err = captured.err.replace(str(app_log_dir), _LOG_ROOT_PLACEHOLDER).replace(
        true_newest_ts, _NEWEST_TS_PLACEHOLDER
    )
    assert normalized_err == snapshot
