---
id: "project/policy/conventions"
type: "policy"
scope: "project"
description: "Code conventions observed in instrukt_ai_logging: snake_case Python with type hints, ruff formatting at line-length 100, future annotations, stdlib-only runtime."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
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
  - Ruff with `line-length = 100`, `target-version = "py311"`.
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
  `{APP}_MUTED_LOGGERS`, plus global `INSTRUKT_AI_LOG_ROOT`. Add capability
  behind existing knobs before introducing a new env var (per `AGENTS.md`).
- **Commits and CI:** Pre-commit hooks (`.pre-commit-config.yaml`) run
  `telec code lint` and `telec code test` plus a guard against hardcoded
  `/Users/...` or `/home/...` paths in markdown.

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

- `telec code lint` (ruff) on pre-commit and in CI (`release.yml` runs
  `uv run -m ruff check .`).
- `telec code test` (pytest) on pre-commit and in CI.
- `[tool.setuptools.packages.find]` is scoped to `include = ["instrukt_ai_logging*"]`
  so accidental top-level modules cannot be packaged.
- The hardcoded-HOME-path hook in `.pre-commit-config.yaml` blocks commits to
  `*.md` files containing absolute user paths.

## Exceptions

- Adding a runtime dependency requires explicit reasoning in the commit body
  and an update to `pyproject.toml` plus `uv.lock`.
- Public API changes (anything in `instrukt_ai_logging/__init__.py::__all__`,
  the env-var names, or the log file layout) are breaking and require a major
  or minor version bump via the auto-release flow.
