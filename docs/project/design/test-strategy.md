---
id: "project/design/test-strategy"
type: "design"
scope: "project"
description: "Test strategy for instrukt_ai_logging: pytest unit tests in tests/, one file per source module, isolated via tmp_path and monkeypatch fixtures."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
---

# Test Strategy — Design

## Purpose

Verify the logging contract end-to-end at unit granularity: env-var parsing,
handler wiring, format output, file resolution, multi-file merge ordering,
follow-mode rotation handling, and rotation config emission. The tests are the
contract's executable spec — they fail when the public behavior changes.

## Inputs/Outputs

Inputs:

- The five test modules under `tests/`, each mirroring a concern in the source:
  - `test_configure_logging.py` — configuration semantics, spotlight, muting,
    `**kv` emission.
  - `test_trace_logging.py` — TRACE level addition and filtering.
  - `test_log_aggregation.py` — `resolve_log_files` and
    `iter_recent_log_lines_merged` behavior, including mtime pre-filter and
    multi-line continuation handling.
  - `test_cli_follow.py` — `iter_follow_lines` reads only appended lines after
    `start_at_end=True`.

- `test_install.py` — user-space rotation assets: conf/scheduler-unit
  emission and idempotent ensure, driven through `configure_logging` and the
  `instrukt-ai-log-setup` entry surface with the scheduler subprocess boundary
  always faked. No test in this repository executes a real subprocess:
  third-party rotator/scheduler behavior (newsyslog, logrotate, launchctl,
  systemctl) is out of test scope — only this library's own logic is tested.

Outputs:

- A pytest run via `uv run pytest` (or `telec code test`) whose pass/fail status
  gates pre-commit hooks and CI.

## Invariants

- **One test module per source concern.** Each `instrukt_ai_logging/<module>.py`
  has at least one corresponding `tests/test_<module>.py` (or, for the
  multi-faceted `logging.py`, multiple test files split by concern).
- **No shared mutable state across tests.** Logging is a process-wide singleton;
  isolation is enforced by:
  - The `isolated_logging` fixture in `test_configure_logging.py` that snapshots
    and restores `logging.root.handlers` and `logging.root.level`.

- Per-test `TemporaryDirectory()` plus `monkeypatch.setenv("XDG_STATE_HOME", tmp)`
  — the platform's own XDG mechanism — so no test writes to the user's real
  `~/.local/state/instrukt-ai/` tree.

- **Quiet output.** `pyproject.toml` sets `addopts = "-q"` and
  `testpaths = ["tests"]`.

- **Non-negotiable time budgets.** `pytest-timeout` enforces a 5-second
  per-test signal timeout and a 90-second session timeout via
  `[tool.pytest.ini_options]` (`timeout=5`, `timeout_method="signal"`,
  `session_timeout=90`, `--strict-config --strict-markers`). The whole suite
  completes in seconds. A hanging or over-budget test is a defect to fix —
  split, rewrite, or remove — never a reason to wait or raise the budget.
- **Fully hermetic.** An autouse `tests/conftest.py` fixture fakes the
  scheduler subprocess seam suite-wide and isolates `HOME` and
  `XDG_STATE_HOME` to `tmp_path`; no test touches the real user domain
  (`~/Library/LaunchAgents`, `~/.config`, `~/.local/state`) or any real
  binary.

## Primary flows

Standard test setup:

```
fixture creates TemporaryDirectory + monkeypatch.setenv(XDG_STATE_HOME, tmp)
  → call configure_logging("teleclaude") (or get_logger())
  → emit log records via standard logging.getLogger(...).info(...)
  → read the resulting file with _read_text(path)
  → assert on substrings (e.g. 'logger=teleclaude.core', 'msg="..."')
```

Rotation-asset test setup (scheduler subprocess boundary faked, files real):

```
fixture creates TemporaryDirectory + monkeypatch.setenv(XDG_STATE_HOME/HOME, tmp)
  + monkeypatch of the scheduler subprocess boundary (launchctl/systemctl)
  → drive configure_logging("teleclaude") or instrukt-ai-log-setup main()
  → read the emitted conf / scheduler-unit files under the tmp user dirs
  → assert on protocol-significant tokens, idempotence across a second run,
    warning lines in the log file, and exit status
```

CLI follow test:

```
spawn iter_follow_lines() in a thread with start_at_end=True, max_lines, max_seconds
  → main thread sleeps briefly so reader seeks to EOF
  → main thread appends lines
  → join thread; assert reader observed only the appended lines
```

## Failure modes

- **Race in `test_iter_follow_lines_yields_appended_lines_only`.** The test relies
  on a `time.sleep(0.05)` to let the reader seek to end before appends start.
  On heavily loaded CI runners this could flake; `max_seconds=2` and
  `max_lines=2` bound the worst case.
- **Filesystem time resolution in mtime pre-filter test.** `os.utime` is used to
  force a stale mtime for `stale.log` so the merged-read pre-filter can be
  exercised deterministically.
- **No fakes for `WatchedFileHandler`.** Tests write to real temp files and read
  them back; this catches encoding and rotation issues that mocks would hide.
- **Missing tests for redaction patterns.** `_REDACTION_PATTERNS` and
  `_truncate_text` have no direct unit coverage. They are exercised only
  transitively via the formatter; add focused tests when changing them.
