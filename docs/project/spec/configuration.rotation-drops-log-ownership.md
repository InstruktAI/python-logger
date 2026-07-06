---
description: "Runtime configuration contract for instrukt_ai_logging: four per-app environment variables and one fixed, predictable log location — no global override."
---

# Configuration — Spec

## What it is

The full runtime configuration surface of the library. There are no config
files — every knob is an environment variable. Per-app variables are namespaced
by an `{APP}` prefix derived from the `name` argument passed to
`configure_logging(...)`. The log location is a fixed rule, not a knob: there
is no global override variable.

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

These four variables are the entire environment contract. The library
additionally _honors_ `XDG_STATE_HOME` because the log location follows the XDG
Base Directory spec — that is platform compliance, not an app knob.

In-process configuration (`configure_logging(...)` keyword args):

- `source: str | None` — logical identity of the producing process within an
  app. When `None`, the file is `<app>.log`. When set (e.g. `"cron"`,
  `"docs-watch"`), the file is `<source>.log` under the same app directory.
  The `.log` extension is always appended.
- `max_message_chars: int = 4000` — per-record truncation budget; values longer
  than this are suffixed with `…(truncated)`.

Resolved log file path (identical on macOS and Linux):

- `$XDG_STATE_HOME/instrukt-ai/<app>/<source-or-app>.log`
  (`$XDG_STATE_HOME` falls back to `~/.local/state` when unset, per the XDG
  Base Directory spec)

## Allowed values

- Logger prefix matching is dotted-namespace prefix match: `httpcore` matches
  `httpcore` and `httpcore.http11` but not `httpcore-x`.
- `{APP}_THIRD_PARTY_LOGGERS` and `{APP}_MUTED_LOGGERS` parse as
  comma-separated; whitespace around items is stripped, empty items are dropped.
- Level names are case-insensitive; unrecognized names fall back to the
  function-level default (`INFO` for app, `WARNING` for third-party) via
  `_level_name_to_int`.

## Known caveats

- Env vars are read **once** at `configure_logging(...)` time. Changing them in
  the same process after configuration has no effect — call again to re-apply.
- App-prefix logger gets its level set explicitly; `{APP}_THIRD_PARTY_LOGGERS`
  entries that overlap the app prefix are skipped to avoid clobbering it.
- `{APP}_MUTED_LOGGERS` runs after spotlight assignment, so muting takes
  precedence over spotlighting for the same prefix.
- The log root is user-writable by construction; no installer step or elevated
  permissions are involved. Tests and CI isolate the filesystem by setting
  `XDG_STATE_HOME` to a temporary directory — the platform's own mechanism,
  not an app-specific hook.
