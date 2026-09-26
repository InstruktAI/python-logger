---
id: "project/policy/conventions"
type: "policy"
scope: "project"
description: "Code conventions observed in instrukt_ai_logging: snake_case Python with type hints, ruff formatting at line-length 120, future annotations, stdlib-only runtime."
---

# Project Conventions — Policy

## Rules

- **Python target:** `python_requires = ">=3.11"` and `target-version = "py311"`
  in `[tool.ruff]`. Use only syntax and stdlib features available on 3.11+.
- **Stdlib only at runtime.** `[project] dependencies = []`. Add a runtime
  dependency only with explicit justification — the project's value
  proposition includes "drop-in, no transitive deps".
- **Naming:**
  - Modules and functions: `snake_case`
    (`configure_logging`, `iter_recent_log_lines_merged`).
  - Classes: `PascalCase` (`InstruktAILogger`, `LogfmtFormatter`,
    `UtcMillisFormatter`, `LoggingContract`).
  - Internal helpers: leading underscore (`_normalize_env_prefix`,
    `_ThirdPartySelectorFilter`, `_REDACTION_PATTERNS`).
  - Distribution name uses hyphens (`instruktai-python-logger`); module name
    uses underscores (`instrukt_ai_logging`).
- **Imports:**
  - `from __future__ import annotations` at the top of every source module.
  - stdlib first, then first-party (`from instrukt_ai_logging.logging import ...`).
- **Type hints required.** All public functions and classes are annotated;
  `py.typed` is shipped under `instrukt_ai_logging/` and declared in
  `[tool.setuptools.package-data]`.
- **Formatting and lint:**
  - Ruff with `line-length = 120`, `target-version = "py311"`.
  - Lint: `uv run ruff check .` (or `telec code lint`).
  - Format: `uv run ruff format .` (or `telec code format`).
- **Tests:**
  - `pytest` with `addopts = "-q"` and `testpaths = ["tests"]`.
  - One test module per source concern (see `project/design/test-strategy`).
  - Run via `uv run pytest` or `telec code test`.
- **Logging output format:** single-line logfmt-ish, ordered as
  `<UTC ms timestamp> level=... logger=... msg="..." [<sorted **kv pairs>] [exc=...]`.
  Do not introduce JSON-first formatting unless a consumer explicitly requires it
  (per `docs/design.md`).

- **Env-var contract is stable:** `{APP}_LOG_LEVEL`,
  `{APP}_THIRD_PARTY_LOG_LEVEL`, `{APP}_THIRD_PARTY_LOGGERS`,
  `{APP}_MUTED_LOGGERS` — these four per-app variables are the entire
  contract. The log location is a fixed rule
  (`$XDG_STATE_HOME/instrukt-ai/{app}/`, fallback `~/.local/state`), not an
  env knob; no override variable exists. Add capability behind existing knobs
  before introducing a new env var (per `AGENTS.md`).

- **Install split (`install` / `install-runtime`):** `make install` performs
  local development setup only (dependencies, tooling, git hooks); it never
  touches host or user machinery. Wiring the per-user rotation scheduler into
  launchd/systemd is an explicit, opt-in step: `make install-runtime`,
  delegating to the `instrukt-ai-log-setup` console script. Consuming services
  invoke `instrukt-ai-log-setup` from their own deploy/setup — the console
  script, not the Make target, is the consumer-facing entry. (Mirrors the
  itsUP `install`/`install-runtime` convention at per-user granularity.)

- **Commits and CI:** `telec code commit` runs format and lint in-process
  before creating the commit (the `pre-commit` framework is not in use here;
  there is no `.pre-commit-config.yaml`, and the git `pre-commit` hook itself
  only guards against partially staged files). The hardcoded-HOME-path guard
  against `/Users/...` or `/home/...` paths in markdown runs as part of that
  same lint pass, inside `telec code lint`'s guardrails lane. Tests are not
  gated by a git hook: TeleClaude's checkpoint system requires a test run at
  the next turn boundary whenever changed source falls under
  `instrukt_ai_logging/**`. CI (`release.yml`) re-runs both ruff and pytest on
  every push.

## Rationale

- A logging library in the import path of every service must not cause
  dependency churn — hence the stdlib-only runtime invariant.
- A small, stable env-var surface is easier to teach, document, and grep for
  across services than a sprawling option set.
- `from __future__ import annotations` keeps signatures cheap to read on 3.11
  and ready for any deferred-eval changes upstream.
- Single-line logfmt output is the precondition for a useful tail window —
  multi-line records would defeat the contract's primary intent.

## Scope

Applies to all source files under `instrukt_ai_logging/`, all tests under
`tests/`, and any documentation or tooling that affects the published API.

## Enforcement

- `telec code lint` (ruff), run in-process by `telec code commit` before
  every commit, and again in CI (`release.yml`'s "Lint + tests" step).
- `telec code test` (pytest), required by TeleClaude's checkpoint system at
  the next turn boundary after a change under `instrukt_ai_logging/**`, and
  run again in CI (`release.yml`'s "Lint + tests" step).
- `[tool.setuptools.packages.find]` is scoped to `include = ["instrukt_ai_logging*"]`
  so accidental top-level modules cannot be packaged.
- The hardcoded-HOME-path guardrail, run as part of `telec code lint`, blocks
  commits to `*.md` files containing absolute user paths.

## Exceptions

- Adding a runtime dependency requires explicit reasoning in the commit body
  and an update to `pyproject.toml` plus `uv.lock`.
- Public API changes (anything in `instrukt_ai_logging/__init__.py::__all__`,
  the env-var names, or the log file layout) are breaking and require a major
  or minor version bump via the auto-release flow.
