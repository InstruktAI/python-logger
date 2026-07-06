---
description: "Architecture of the instrukt_ai_logging library: a stdlib-only Python package whose logging and rotation both live entirely in user space — one predictable XDG log location, rotation run as the producing user, zero root involvement."
---

# Project Architecture — Design

## Purpose

`instruktai-python-logger` (PyPI dist) ships a single Python package,
`instrukt_ai_logging`, that enforces a shared logging contract across InstruktAI
services. The library is consumed by every Python service in the org so that one
CLI (`instrukt-ai-logs`) and one set of env-var knobs work uniformly.

Two constraints dominate the design:

- Logs must remain queryable from a tail window (`docs/design.md`) — third-party
  debug/info noise must not push service signal out.
- The entire logging lifecycle — writing, locating, and rotating logs — runs as
  the producing user. Root appears nowhere: no `/etc` configuration, no sudo
  step, no system rotation daemon touching these files. Ownership problems are
  structurally unexpressible, not compensated for.

## Inputs/Outputs

Inputs:

- App identifier passed to `configure_logging(name, source=...)` — a single
  string (e.g. `"teleclaude"`) that is normalized three ways: env-var prefix
  (`TELECLAUDE`), logger prefix (`teleclaude`), filesystem app name
  (`teleclaude`). See `_normalize_env_prefix`, `_normalize_logger_prefix`,
  `_normalize_app_name` in `instrukt_ai_logging/logging.py`.
- Environment variables: `{APP}_LOG_LEVEL`, `{APP}_THIRD_PARTY_LOG_LEVEL`,
  `{APP}_THIRD_PARTY_LOGGERS`, `{APP}_MUTED_LOGGERS`. These four per-app
  variables are the entire configuration surface — there is no log-root
  override variable, flag, or API parameter.
- Optional `source=` to address per-process log files in multi-producer apps.

Outputs:

- A configured root logger with exactly one `WatchedFileHandler` writing
  single-line logfmt records to
  `$XDG_STATE_HOME/instrukt-ai/{app}/{source-or-app}.log` — the one
  predictable, prose-citable location all InstruktAI applications document.
  `$XDG_STATE_HOME` follows the XDG Base Directory spec (fallback
  `~/.local/state` when unset) on **both** macOS and Linux.
- `configure_logging(...)` returns the resolved log file `Path`.
- User-space rotation assets, ensured transparently and idempotently at
  configure time: a rotation conf under `~/.config/instrukt-ai/` plus a
  per-user scheduler unit (launchd LaunchAgent on macOS, systemd user timer on
  Linux) that runs the platform rotator **as the user**.
- `instrukt-ai-logs` CLI prints filtered/merged lines from a chosen time window;
  `instrukt-ai-log-setup` runs the same ensure step manually and reports
  rotation-asset status (no sudo; useful for debugging).

## Invariants

- **Stdlib only at runtime.** `pyproject.toml` declares `dependencies = []`.
  Optional `dev` extras are pytest and ruff. Adding a runtime dependency would
  break this invariant.
- **One predictable location, no knobs.** The resolved rule is
  `$XDG_STATE_HOME/instrukt-ai/{app}/` (fallback `~/.local/state`) — identical
  on macOS and Linux. No app-level override exists: no `INSTRUKT_AI_LOG_ROOT`,
  no CLI flag, no `configure_logging` parameter. Tests isolate via
  `XDG_STATE_HOME`, the platform's own mechanism.
- **Rotation runs as the producing user, never root.** The scheduler unit and
  rotator invocation are per-user; rotated and recreated files therefore always
  carry the producer's ownership by construction.
- **One handler per process.** `configure_logging` replaces
  `logging.root.handlers` with a single `WatchedFileHandler`. Verified by
  `tests/test_configure_logging.py::test_configure_logging_uses_single_file_handler`.
- **Logging fails fast at startup.** An unopenable log directory or file raises
  out of `configure_logging`; the host process must not start blind. There is
  deliberately no degraded/fallback mode.
- **One line per event.** `LogfmtFormatter.format` joins parts with spaces and
  escapes embedded newlines via `_escape_quotes`. Exception text has its newlines
  replaced with `\n` before being attached as `exc=...`.
- **Third-party spotlight semantics are deterministic.** `_ThirdPartySelectorFilter`
  always passes records from `app_logger_prefix`; for non-app loggers it allows
  only those matching configured spotlight prefixes (or all, when none are set).
- **Tail-window protection.** Long values are truncated by `_truncate_text` using
  the per-call `max_message_chars` (default 4000). Secrets are scrubbed by
  `_REDACTION_PATTERNS` (Telegram bot tokens, Bearer tokens, OpenAI `sk-` keys).
- **Rotation must keep working around a live writer.** `WatchedFileHandler`
  reopens on inode change; `iter_follow_lines` in the CLI detects rotation and
  truncation.

## Primary flows

Configuration (called once at process start):

```
caller passes name="teleclaude"
  → normalize into env_prefix / logger_prefix / app_name
  → coerce all existing loggers to InstruktAILogger (so .info(msg, **kv) works)
  → read env vars; compute our_level, third_party_level, spotlight, muted
  → resolve $XDG_STATE_HOME/instrukt-ai/{app}/, ensure dir, attach single
    WatchedFileHandler with LogfmtFormatter (any OSError raises — fail fast)
  → set per-prefix levels for app, spotlight, muted
  → ensure user-space rotation assets (idempotent; failures warn, see below)
  → return resolved Path
```

Rotation-ensure flow (inside `configure_logging`, and manually via
`instrukt-ai-log-setup`):

```
derive desired conf + scheduler-unit content from the resolved log root
  → compare with what is on disk; rewrite only on drift (idempotent re-runs)
  → macOS: ~/.config/instrukt-ai/newsyslog.conf (one glob line
    "<root>/*/*.log 640 5 50000 * ZG": 5 gzipped archives at 50 MB) +
    ~/Library/LaunchAgents/ai.instrukt.log-rotate.plist running
    /usr/sbin/newsyslog -f <conf> every 30 min; bootstrap via launchctl
  → Linux: ~/.config/instrukt-ai/logrotate.conf (size 50M, rotate 5, compress,
    delaycompress, missingok, notifempty) + systemd user service+timer running
    logrotate --state $XDG_STATE_HOME/instrukt-ai/logrotate.state <conf>;
    enable via systemctl --user
  → any ensure failure emits a WARNING through the configured logger and
    configure_logging continues — rotation bootstrap is not logging
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

## Failure modes

- **Unwritable log dir or file.** `configure_logging` raises (`_ensure_log_dir`
  mkdir or `WatchedFileHandler` open). Intentional fail-fast: logging is an
  essential subsystem and a process that cannot write durable logs must not
  run. Because path, writer, and rotator all live in user space, this only
  occurs on genuine local misconfiguration.
- **Rotation-ensure failure.** `launchctl`/`systemctl` unavailable or refusing
  (e.g. no user service manager in a container): a WARNING is logged, logging
  itself continues, and log growth is unbounded until the operator resolves
  it — surfaced, never silent, never fatal.
- **New producers/apps.** The rotation conf covers the log root with a glob
  evaluated at rotation time (newsyslog `G` flag / logrotate glob), so new
  `{app}`/`{source}` files are rotated without any re-install step.
- **Empty/malformed timestamps in merged read.** `parse_log_timestamp` returns
  `None` for unparseable lines; `iter_recent_log_lines_merged` treats those as
  continuation lines and inherits the previous parsed timestamp from the same
  file (covered by `test_iter_recent_log_lines_merged_keeps_continuation_lines_with_parent`).
- **Rotation during follow.** `iter_follow_lines` detects inode change and
  reopens; truncation is detected by `f.tell() > st.st_size` and rewinds.
- **Large/sensitive payloads.** Mitigated by `_truncate_text` and
  `_REDACTION_PATTERNS`. Adding new redactions requires "strong justification"
  per the inline comment — they execute on every log line.
