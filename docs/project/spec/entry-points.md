---
id: "project/spec/entry-points"
type: "spec"
scope: "project"
description: "Entry points exposed by instrukt_ai_logging: two console scripts (instrukt-ai-logs, instrukt-ai-log-setup) and a Python API re-exported from the package root."
---

# Entry Points — Spec

## What it is

The public surface of the `instrukt_ai_logging` package: console scripts wired
through `[project.scripts]` and Python symbols listed in
`instrukt_ai_logging/__init__.py::__all__`. Anything outside this list is
internal and may change without a version bump.

## Canonical fields

Console scripts (from `[project.scripts]`):

- `instrukt-ai-logs = "instrukt_ai_logging.cli:main"` — read recent log lines
  with keep/drop regex filters (`--grep` keeps, `--exclude` drops, applied after
  `--grep`), time window (`--since`), per-source stem selection
  (`--logs`, alias `--include`), and `tail -f`-style follow (`-f` / `--follow`).

- `instrukt-ai-log-setup = "instrukt_ai_logging.install:main"` — the
  runtime-install entry: idempotently wire the per-user rotation assets (conf
  plus scheduler unit) and print a status report (resolved log root, conf
  paths, scheduler state). User-space only; requires no sudo. Run once at
  deploy — directly or via `make install-runtime`; re-runs on an already-wired
  machine report healthy.

Python package API (`instrukt_ai_logging/__init__.py::__all__`):

- `__version__` — string resolved via `importlib.metadata` at import time.
- `configure_logging(name, *, source=None, max_message_chars=4000) -> Path` —
  configure root logging per the contract; returns the resolved log file path.
- `get_logger(name) -> InstruktAILogger` — return a logger that accepts
  arbitrary `**kv` fields.
- `InstruktAILogger` — `logging.Logger` subclass that captures `**kv` kwargs
  and routes them through `extra={"kv": ...}` to the formatter.
- `InstruktAILoggerProtocol` — `runtime_checkable` Protocol describing the
  same surface for type-only contexts.
- `resolve_log_file(app_name, *, source=None) -> Path` — canonical path
  builder.
- `resolve_log_files(app_name, *, stems=None) -> list[Path]` — enumerate the
  app's log files, optionally filtered by exact stem, including rotated `.gz`
  archives so `--since` time-window reads span compressed rotation history.
- `TRACE` — integer level value `5`, registered with `logging.addLevelName`
  and assigned as `logging.TRACE` for downstream introspection.

CLI argument surfaces:

- `instrukt-ai-logs <app> [--since 10m] [--follow] [--grep PATTERN] [--exclude PATTERN] [--logs/--include stem1,stem2] [--version]`

- `instrukt-ai-log-setup` (no arguments — the log root is the fixed
  `$XDG_STATE_HOME/instrukt-ai` rule and the ensure step is idempotent)

## Allowed values

- Names accepted by `configure_logging` are normalized through three regex
  passes (env prefix, logger prefix, fs app name). Any string with at least one
  alphanumeric character will produce a valid contract; punctuation is collapsed.
- `--since` accepts an integer suffixed with `s|m|h|d` (parsed by `parse_since`).
- `--logs` (alias `--include`) is a comma-separated list of stems; matching is
  exact-stem (`cron` matches `cron.log`, `cron.log.0`, never `cron-backup.log`).

## Known caveats

- Importing the package does not configure logging. Callers must invoke
  `configure_logging(...)` explicitly during process start; otherwise no
  handler is attached and records fall back to Python's default behavior.
- `configure_logging` replaces (does not extend) `logging.root.handlers`. Code
  that pre-attaches handlers will lose them.

- `configure_logging(...)` never sets up rotation. A machine that has not run
  `instrukt-ai-log-setup` (or `make install-runtime`) writes logs without a
  rotation scheduler, and log growth is unbounded until that one-time setup
  step runs.

- The `__version__` resolution catches a bare `Exception` and falls back to
  `"0.0.0"` when the package is loaded outside an installed distribution.
