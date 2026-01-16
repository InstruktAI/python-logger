# Agent instructions

This repository defines the logging standard used across InstruktAI Python services.

Before changing anything, read `docs/design.md`.

## Scope

- Keep the env var contract stable:
  - `{APP}_LOG_LEVEL`
  - `{APP}_THIRD_PARTY_LOG_LEVEL`
  - `{APP}_THIRD_PARTY_LOGGERS`
  - `{APP}_MUTED_LOGGERS`
  - `INSTRUKT_AI_LOG_ROOT`
- Prefer adding capabilities behind existing knobs over introducing new knobs.

## Behavioral invariants (do not break)

- Logs remain tail-friendly: prevent third-party spam from pushing signal out of the tail window.
- Output stays human-readable, single-line per event.
- Default log destination targets `/var/log/instrukt-ai/{app}/{app}.log`.
- Always support explicit override via `INSTRUKT_AI_LOG_ROOT`.
- External rotation must be supported (don’t “fight” logrotate/newsyslog).
- Redact secrets and truncate very long lines (tail killers).

## Implementation notes (for future work)

- Use Python stdlib `logging` (avoid bespoke logging frameworks unless necessary).
- Third-party selection is by logger prefix (dotted namespace), e.g. `httpcore` means `httpcore.*`.
- The “ours vs third-party” boundary should be deterministic and should not require a filesystem layout change.
- Provide a unified CLI (`instrukt-ai-logs`) for consistent retrieval and time slicing across platforms.

## Dev workflow expectations

- Add unit tests for any behavior changes.
- Run formatting: `uv run ruff format .`
- Run linting: `uv run ruff check .`
- Run tests: `uv run pytest`
