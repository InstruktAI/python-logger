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
under `/var/log/instrukt-ai/{app}/`. The CLI merges them transparently
(see below).

## Environment variables (contract)

Per-app prefix model (example uses `TELECLAUDE_`):

- `TELECLAUDE_LOG_LEVEL`
- `TELECLAUDE_THIRD_PARTY_LOG_LEVEL`
- `TELECLAUDE_THIRD_PARTY_LOGGERS` (comma-separated logger prefixes to spotlight, e.g. `httpcore,telegram`)
- `TELECLAUDE_MUTED_LOGGERS` (comma-separated logger prefixes to force to WARNING+, e.g. `teleclaude.cli.tui`)

Global:

- `INSTRUKT_AI_LOG_ROOT` (optional log root override)

## Log location (contract)

Default target:

- `/var/log/instrukt-ai/{app}/{app}.log`

The installer for each service is expected to create the directory and set write permissions for the daemon user. If the default location is not writable, the implementation will fall back to a user-writable directory and/or require `INSTRUKT_AI_LOG_ROOT`.

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
