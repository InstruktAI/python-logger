# `instruktai-python-logger`

Centralized logging utilities for InstruktAI Python services.

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

## Environment variables (contract)

Per-app prefix model (example uses `TELECLAUDE_`):

- `TELECLAUDE_LOG_LEVEL`
- `TELECLAUDE_THIRD_PARTY_LOG_LEVEL`
- `TELECLAUDE_THIRD_PARTY_LOGGERS` (comma-separated logger prefixes, e.g. `httpcore,telegram`)

Global:

- `INSTRUKT_AI_LOG_ROOT` (optional log root override)

## Log location (contract)

Default target:

- `/var/log/instrukt-ai/{app}/{app}.log`

The installer for each service is expected to create the directory and set write permissions for the daemon user. If the default location is not writable, the implementation will fall back to a user-writable directory and/or require `INSTRUKT_AI_LOG_ROOT`.
