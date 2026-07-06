# InstruktAI Python Logger

Centralized logging utilities for Python services.

This repo provides a shared, consistent logging contract (env vars + output format + log location) intended to keep logs highly queryable (including by AIs that only read a tail window).

Background and rationale live in `docs/design.md`.
Publishing notes live in `docs/publishing.md`.

## Install (editable, local workspace)

From PyPI (recommended):

```bash
pip install instruktai-python-logger
```

From GitHub:

```bash
pip install git+ssh://git@github.com/InstruktAI/python-logger.git
```

## API

- Python entrypoint: `instrukt_ai_logging.configure_logging(...)`
- Logger helper: `instrukt_ai_logging.get_logger(name)` (named `**kv` logging)
- CLI entrypoint: `instrukt-ai-logs` (reads recent log lines)

Example:

```py
import logging
from instrukt_ai_logging import configure_logging

configure_logging("teleclaude")
logger = logging.getLogger("teleclaude.core")
logger.info("job_started", job_id="abc123", user_id=123)
```

### Per-process log files (multi-producer apps)

When several processes belong to the same app (a daemon plus a watcher plus a
cron, for example), each one can own its own file under the same app directory
by passing `source=`:

```py
configure_logging("teleclaude")                       # → teleclaude.log (default)
configure_logging("teleclaude", source="docs-watch")  # → docs-watch.log
configure_logging("teleclaude", source="cron")        # → cron.log
```

The `.log` extension is always appended; pass the bare stem. Files all live
under `$XDG_STATE_HOME/instrukt-ai/{app}/` (fallback `~/.local/state`). The CLI
merges them transparently (see below).

## Environment variables (contract)

Per-app prefix model (example uses `TELECLAUDE_`):

- `TELECLAUDE_LOG_LEVEL`
- `TELECLAUDE_THIRD_PARTY_LOG_LEVEL`
- `TELECLAUDE_THIRD_PARTY_LOGGERS` (comma-separated logger prefixes to spotlight, e.g. `httpcore,telegram`)
- `TELECLAUDE_MUTED_LOGGERS` (comma-separated logger prefixes to force to WARNING+, e.g. `teleclaude.cli.tui`)

These four per-app variables are the entire contract. There is no log-root
override variable — the location is a fixed rule (see below).

## Log location (contract)

Every app's logs live at the same predictable, prose-citable location on both
macOS and Linux:

- `$XDG_STATE_HOME/instrukt-ai/{app}/{app}.log` (fallback `~/.local/state`,
  per the XDG Base Directory spec)

This path is always user-writable — no installer step, no sudo, no elevated
permissions. `configure_logging(...)` raises immediately if the log file
cannot be opened; logging is an essential subsystem and a process that cannot
write its logs must not start blind.

## Rotation

Rotation is transparent and runs entirely in user space:
`configure_logging(...)` idempotently ensures a per-user rotation conf plus a
per-user scheduler (a launchd LaunchAgent on macOS running `newsyslog`, a
systemd user timer on Linux running `logrotate`) on every process start. No
`/etc` configuration, no sudo, and no system rotation daemon ever touches
these files, so rotated/recreated logs always stay owned by the producing
user. Run `instrukt-ai-log-setup` to check rotation-asset status manually;
normal operation never requires it.

## CLI

```bash
# Last 10 minutes (default), follows
instrukt-ai-logs teleclaude -f

# Last 2 hours
instrukt-ai-logs teleclaude --since 2h

# Filter with regex
instrukt-ai-logs teleclaude --since 10m --grep 'logger=teleclaude'

# Follow (tail -f style) after printing the --since window
instrukt-ai-logs teleclaude --since 10m --follow

# Restrict to specific source streams (per-process files)
instrukt-ai-logs teleclaude --since 1h --logs=cron,docs-watch
```

Without `--logs`, every `*.log*` file in the app directory is merged by
timestamp (rotation suffixes included). With `--logs=stem1,stem2`, only files
whose stem matches an entry are read — exact stem match, so `--logs=cron`
picks `cron.log`, `cron.log.0`, `cron.log.1` and never `cron-backup.log`.
Follow mode reads each selected file with one polling thread per file.
