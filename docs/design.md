# Design

This document captures the design intent and constraints for `instrukt_ai_logging`.

## Primary intent

Logs must remain meaningfully queryable even when a consumer (especially an AI) only reads a limited “tail window” (e.g. the last N characters). The most common failure mode is third‑party debug/info spam pushing important service logs out of the window.

## Core decisions

### One primary log stream per service

- Prefer a single primary file per service (rotated) instead of many per-component files.
- Query by logger namespace and key/value fields inside the log line.

### Local-first storage; predictable path

- Canonical target path is `/var/log/instrukt-ai/{app}/{app}.log`.
- Service installers may prompt for sudo to create directories and set permissions.
- The library must support an explicit override via `INSTRUKT_AI_LOG_ROOT`.

### Keep logs human-readable (text), but structured enough for machines

- Use a consistent single-line format.
- Include lightweight key/value fields when helpful.
- Avoid JSON-first unless a consumer explicitly requires it.

### Minimal knobs; stable contract

Per-app prefix contract:

- `{APP}_LOG_LEVEL` (service logs)
- `{APP}_THIRD_PARTY_LOG_LEVEL` (verbosity for third-party logs when enabled)
- `{APP}_THIRD_PARTY_LOGGERS` (comma-separated logger prefixes to "spotlight")
- `{APP}_MUTED_LOGGERS` (comma-separated logger prefixes to force to WARNING+)

Selection semantics:

- If `{APP}_THIRD_PARTY_LOGGERS` is set, only those prefixes are allowed to emit at `{APP}_THIRD_PARTY_LOG_LEVEL`; all other third-party logs are forced to WARNING+.
- If `{APP}_THIRD_PARTY_LOGGERS` is unset/empty, `{APP}_THIRD_PARTY_LOG_LEVEL` applies to all third-party logs.
- `{APP}_MUTED_LOGGERS` forces matched prefixes to WARNING+ regardless of whether they are app or third-party loggers. Use this to silence noisy app sub-namespaces.

### Infra logs are separate

Application logs (Python logging) and service-manager/process logs (stdout/stderr, crash-before-logging) are different layers. The unified CLI can expose both, but the storage contract for this project focuses on application logs.

## Non-negotiables

- Rotation must exist (prefer OS tooling; library should not prevent external rotation).
- No secret leakage (redaction must be part of the standard).
- Large payloads must not dominate the tail window (truncate very long lines).

