---
id: "project/design/test-strategy"
type: "design"
scope: "project"
description: "Test invariants for instrukt_ai_logging: hermeticity, isolation, time budgets, one module per concern. Constraints on future tests — the suite itself is its own documentation."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
---

# Test Strategy — Design

## Purpose

Constrain how this library is tested. The tests are the contract's executable
spec — they fail when the public behavior changes. This document holds only
the invariants that bind every current and future test; it does not describe
individual tests or their entry points — the suite under `tests/` is its own
documentation.

## Inputs/Outputs

Inputs: the pytest suite under `tests/`. Outputs: a `uv run pytest` (or
`telec code test`) pass/fail status that gates pre-commit hooks and CI.

## Invariants

- **One test module per source concern.** Each `instrukt_ai_logging/<module>.py`
  has at least one corresponding `tests/test_<module>.py` (or, for the
  multi-faceted `logging.py`, multiple test files split by concern).
- **No shared mutable state across tests.** Logging is a process-wide
  singleton; tests that configure it snapshot and restore
  `logging.root.handlers` and `logging.root.level`.
- **Filesystem isolation via the platform's own mechanism.** Per-test
  `TemporaryDirectory()` plus `monkeypatch.setenv("XDG_STATE_HOME", tmp)` — no
  test writes to the user's real `~/.local/state/instrukt-ai/` tree.
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
  (`~/Library/LaunchAgents`, `~/.config`, `~/.local/state`) or executes any
  real subprocess. Third-party rotator/scheduler behavior (newsyslog,
  logrotate, launchctl, systemctl) is out of test scope — only this library's
  own logic is tested.

## Primary flows

None prescribed. Tests follow the invariants above and the conventions
already present in the suite; per-test setup recipes live in the tests
themselves, not here.

## Failure modes

- **A test that cannot satisfy the invariants does not get written.**
  Behavior that requires a real scheduler binary, real network, or the real
  user home tree is out of automated-test scope; it is verified by an
  explicit operator/deployment action instead.
