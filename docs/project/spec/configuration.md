---
id: "project/spec/configuration"
type: "spec"
scope: "project"
description: "Runtime configuration contract for instrukt_ai_logging: per-app environment variables and the global INSTRUKT_AI_LOG_ROOT override."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
---

# Configuration — Spec

## What it is

The full runtime configuration surface of the library. There are no config
files — every knob is an environment variable. Per-app variables are namespaced
by an `{APP}` prefix derived from the `name` argument passed to
`configure_logging(...)`. One global variable controls the log root.

## Canonical fields

Per-app environment variables (where `{APP}` is the normalized env prefix,
e.g. `TELECLAUDE` for `configure_logging("teleclaude")`):

- `{APP}_LOG_LEVEL` — level for loggers under the app's prefix
  (e.g. `teleclaude.*`). Default: `INFO`. Accepted: any name resolvable via
  `getattr(logging, name)` (`TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`,
  `CRITICAL`).
- `{APP}_THIRD_PARTY_LOG_LEVEL` — level applied to third-party loggers when
  they are allowed to emit. Default: `WARNING`.
- `{APP}_THIRD_PARTY_LOGGERS` — comma-separated logger prefixes to "spotlight"
  (e.g. `httpcore,telegram`). When set, only these non-app prefixes may emit at
  `{APP}_THIRD_PARTY_LOG_LEVEL`; all other third-party loggers are forced to
  WARNING+ via the root logger. When unset, the third-party level applies to
  all non-app loggers.
- `{APP}_MUTED_LOGGERS` — comma-separated logger prefixes forced to WARNING+.
  Applies to both app and third-party prefixes; use it to silence noisy
  sub-namespaces (e.g. `teleclaude.cli.tui`).

Global environment variables:

- `INSTRUKT_AI_LOG_ROOT` — base directory under which `<app>/<source>.log`
  files live. When unset, defaults to `/var/log/instrukt-ai`.

In-process configuration (`configure_logging(...)` keyword args):

- `source: str | None` — logical identity of the producing process within an
  app. When `None`, the file is `<app>.log`. When set (e.g. `"cron"`,
  `"docs-watch"`), the file is `<source>.log` under the same app directory.
  The `.log` extension is always appended.
- `max_message_chars: int = 4000` — per-record truncation budget; values longer
  than this are suffixed with `…(truncated)`.

Resolved log file path:

- `<INSTRUKT_AI_LOG_ROOT or /var/log/instrukt-ai>/<app>/<source-or-app>.log`

## Allowed values

- Logger prefix matching is dotted-namespace prefix match: `httpcore` matches
  `httpcore` and `httpcore.http11` but not `httpcore-x`.
- `{APP}_THIRD_PARTY_LOGGERS` and `{APP}_MUTED_LOGGERS` parse as
  comma-separated; whitespace around items is stripped, empty items are dropped.
- Level names are case-insensitive; unrecognized names fall back to the
  function-level default (`INFO` for app, `WARNING` for third-party) via
  `_level_name_to_int`.
- `INSTRUKT_AI_LOG_ROOT` is `expanduser`-ed, so `~/logs` works for dev.

## Known caveats

- Env vars are read **once** at `configure_logging(...)` time. Changing them in
  the same process after configuration has no effect — call again to re-apply.
- App-prefix logger gets its level set explicitly; `{APP}_THIRD_PARTY_LOGGERS`
  entries that overlap the app prefix are skipped to avoid clobbering it.
- `{APP}_MUTED_LOGGERS` runs after spotlight assignment, so muting takes
  precedence over spotlighting for the same prefix.
- The default `/var/log/instrukt-ai/<app>/` typically requires the service's
  installer to create the directory and grant the daemon user write access.
  In dev or CI, set `INSTRUKT_AI_LOG_ROOT` to a writable temp directory.
