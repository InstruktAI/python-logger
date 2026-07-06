---
id: "project/design/architecture"
type: "design"
scope: "project"
description: "Architecture of the instrukt_ai_logging library: a stdlib-only Python package with three modules and two console scripts that enforce the InstruktAI logging contract."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
---

# Project Architecture — Design

## Purpose

`instruktai-python-logger` (PyPI dist) ships a single Python package,
`instrukt_ai_logging`, that enforces a shared logging contract across InstruktAI
services. The library is consumed by every Python service in the org so that one
CLI (`instrukt-ai-logs`) and one set of env-var knobs work uniformly.

The dominant design constraint, captured in `docs/design.md`, is that logs must
remain queryable from a tail window — third-party debug/info noise must not push
service signal out. Architecture decisions follow from that constraint.

## Inputs/Outputs

Inputs:

- App identifier passed to `configure_logging(name, source=...)` — a single
  string (e.g. `"teleclaude"`) that is normalized three ways: env-var prefix
  (`TELECLAUDE`), logger prefix (`teleclaude`), filesystem app name
  (`teleclaude`). See `_normalize_env_prefix`, `_normalize_logger_prefix`,
  `_normalize_app_name` in `instrukt_ai_logging/logging.py`.
- Environment variables: `{APP}_LOG_LEVEL`, `{APP}_THIRD_PARTY_LOG_LEVEL`,
  `{APP}_THIRD_PARTY_LOGGERS`, `{APP}_MUTED_LOGGERS`, and the global
  `INSTRUKT_AI_LOG_ROOT`. Documented as the public contract in `README.md`.
- Optional `source=` to address per-process log files in multi-producer apps.

Outputs:

- A configured root logger with exactly one `WatchedFileHandler` writing
  single-line logfmt records to `/var/log/instrukt-ai/{app}/{source-or-app}.log`.
- `configure_logging(...)` returns the resolved log file `Path`.
- `instrukt-ai-logs` CLI prints filtered/merged lines from a chosen time window;
  `instrukt-ai-log-setup` writes platform-appropriate rotation config
  (`/etc/newsyslog.d/instrukt-ai.conf` on macOS,
  `/etc/logrotate.d/instrukt-ai` on Linux).

## Invariants

- **Stdlib only at runtime.** `pyproject.toml` declares `dependencies = []`.
  Optional `dev` extras are pytest and ruff. Adding a runtime dependency would
  break this invariant.

- **One handler per process.** `configure_logging` replaces
  `logging.root.handlers` with a single `WatchedFileHandler`. Verified by
  `tests/test_configure_logging.py::test_configure_logging_uses_single_file_handler`.
- **One line per event.** `LogfmtFormatter.format` joins parts with spaces and
  escapes embedded newlines via `_escape_quotes`. Exception text has its newlines
  replaced with `\n` before being attached as `exc=...`.
- **Third-party spotlight semantics are deterministic.** `_ThirdPartySelectorFilter`
  always passes records from `app_logger_prefix`; for non-app loggers it allows
  only those matching configured spotlight prefixes (or all, when none are set).
- **Tail-window protection.** Long values are truncated by `_truncate_text` using
  the per-call `max_message_chars` (default 4000). Secrets are scrubbed by
  `_REDACTION_PATTERNS` (Telegram bot tokens, Bearer tokens, OpenAI `sk-` keys).
- **External rotation must keep working.** `WatchedFileHandler` reopens on inode
  change; `iter_follow_lines` in the CLI detects rotation and truncation.

## Primary flows

Configuration (called once at process start):

```
caller passes name="teleclaude"
  → normalize into env_prefix / logger_prefix / app_name
  → coerce all existing loggers to InstruktAILogger (so .info(msg, **kv) works)
  → read env vars; compute our_level, third_party_level, spotlight, muted
  → ensure log dir, attach single WatchedFileHandler with LogfmtFormatter
  → set per-prefix levels for app, spotlight, muted
  → return resolved Path
```

Read flow (`instrukt-ai-logs <app>`):

```
parse --since (e.g. "10m") into timedelta
  → resolve_log_files(app, stems=...) globs <log_dir>/*.log* and excludes .gz
  → iter_recent_log_lines_merged() pre-filters by file mtime, then heap-merges
    per-file streams keyed by parsed leading timestamp
  → optional regex grep, then write to stdout
  → if --follow, spawn one polling thread per non-rotation file
```

Rotation install flow (`instrukt-ai-log-setup`):

```
detect platform
  → macOS: enumerate every <log_root>/*/*.log file (newsyslog cannot expand
    globs at rotation time) and emit one explicit line per file with
    "640  5  50000  *  Z" defaults (gzip-compress 5 archives at 50 MB)
  → Linux: write a single logrotate block for "<log_root>/*/*.log"
    with size 50M, rotate 5, compress, delaycompress, missingok, copytruncate
```

## Failure modes

- **Missing log root permission.** `_ensure_log_dir` calls `mkdir(parents=True,
exist_ok=True)` — if `/var/log/instrukt-ai/` is not writable this raises, and
  `configure_logging` likewise raises if the resolved log file cannot be opened.
  This hard failure is intentional: logging is an essential subsystem and must
  fail fast at startup rather than degrade silently. The contract relies on each
  service's installer creating the directory and granting the daemon user write
  access; `INSTRUKT_AI_LOG_ROOT` is the documented override for dev or
  unprivileged contexts.
- **Empty/malformed timestamps in merged read.** `parse_log_timestamp` returns
  `None` for unparseable lines; `iter_recent_log_lines_merged` treats those as
  continuation lines and inherits the previous parsed timestamp from the same
  file (covered by `test_iter_recent_log_lines_merged_keeps_continuation_lines_with_parent`).
- **Rotation during follow.** `iter_follow_lines` detects inode change and
  reopens; truncation is detected by `f.tell() > st.st_size` and rewinds.
- **macOS newsyslog and new producers.** `_install_newsyslog` enumerates files
  at install time. A new `<source>.log` created later is not rotated until
  `instrukt-ai-log-setup --force` is re-run. This is documented in the install
  module docstring and is intentional given newsyslog's lack of glob expansion.

- **Large/sensitive payloads.** Mitigated by `_truncate_text` and
  `_REDACTION_PATTERNS`. Adding new redactions requires "strong justification"
  per the inline comment — they execute on every log line.
