---
id: "project/spec/dependencies"
type: "spec"
scope: "project"
description: "Runtime and development dependencies of instruktai-python-logger. Runtime is stdlib-only by design; dev extras are pytest and ruff."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
---

# Dependencies — Spec

## What it is

The dependency surface declared in `pyproject.toml` for the
`instruktai-python-logger` distribution. The library is intentionally
stdlib-only at runtime so that consuming services do not inherit transitive
dependency conflicts from their logger.

## Canonical fields

Build backend (`[build-system]`):

- `requires = ["setuptools>=69", "wheel"]`
- `build-backend = "setuptools.build_meta"`

Runtime dependencies (`[project] dependencies`):

- _empty_ — no runtime dependencies. The library uses only Python stdlib
  modules (`logging`, `logging.handlers.WatchedFileHandler`, `pathlib`,
  `dataclasses`, `datetime`, `re`, `os`, `sys`, `argparse`, `heapq`,
  `threading`, `time`, `typing`).

Development extras (`[project.optional-dependencies] dev`):

- `pytest>=8`
- `ruff>=0.8`

Toolchain expectations:

- Lockfile managed by `uv` (`uv.lock` checked in; `chore(deps): refresh uv.lock`
  appears in recent commit history).
- Sync dev deps with `uv sync --extra dev` (used by `.github/workflows/release.yml`).

CI-only tools (not declared in `pyproject.toml`):

- GitHub Actions: `actions/checkout@v4`, `actions/setup-python@v5`,
  `astral-sh/setup-uv@v5`, `actions/ai-inference@v2`,
  `softprops/action-gh-release@v2`, `pypa/gh-action-pypi-publish@release/v1`.
- Renovate is configured (`renovate.json` at repo root) for automated updates.

## Allowed values

- Python interpreter: `>=3.11` (`requires-python` in `[project]`,
  `target-version = "py311"` in `[tool.ruff]`).
- Adding a runtime dependency would change this snippet and the
  `project/policy/conventions` snippet — both must be updated together.

## Known caveats

- The package keeps `py.typed` under `instrukt_ai_logging/` and declares it in
  `[tool.setuptools.package-data]` so downstream type checkers see public
  signatures. Removing it would silently break consumer type checks.
- `__version__` is resolved via `importlib.metadata.packages_distributions()` in
  `instrukt_ai_logging/__init__.py`. When the distribution is installed under a
  different name (e.g. local editable + renamed dist), this falls back to
  `"0.0.0"` via the broad `except Exception` guard.
