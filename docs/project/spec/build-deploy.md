---
id: "project/spec/build-deploy"
type: "spec"
scope: "project"
description: "Build and release pipeline for instruktai-python-logger: setuptools build, AI-decided semver bump on push to main, PyPI publish on tag push."
generated_by: "telec-init"
generated_at: "2026-05-06T23:30:00Z"
---

# Build and Deploy — Spec

## What it is

The pipeline that turns a commit on `main` into a tagged GitHub release and a
PyPI publication. Two workflows under `.github/workflows/` cooperate, plus a
Makefile and a pre-commit config that protect the local commit path.

## Canonical fields

Local build/test commands (`Makefile`):

- `make lint` → `telec code lint --all`
- `make test` → `telec code test --all`
- `make format` → `telec code format --all`

Pre-commit (`.pre-commit-config.yaml`):

- `lint` hook → `telec code lint`
- `test` hook → `telec code test`
- `teleclaude-docs-check` hook → blocks commits whose staged `*.md` files
  contain hardcoded `/Users/...` or `/home/...` paths.

Build backend (from `pyproject.toml`):

- `requires = ["setuptools>=69", "wheel"]`
- `build-backend = "setuptools.build_meta"`
- `[tool.setuptools.packages.find] include = ["instrukt_ai_logging*"]`
- `[tool.setuptools.package-data] instrukt_ai_logging = ["py.typed"]`

Release workflow (`.github/workflows/release.yml`):

- Trigger: `push` to `main`, or `workflow_dispatch`.
- Concurrency group `release-main` with `cancel-in-progress: false`.
- Skip step bails out if the head commit subject matches `chore(release):*`
  (prevents recursion after the bot's own release commit).
- Steps: setup Python 3.11, set up `uv`, `uv sync --extra dev`, run
  `uv run -m ruff check .` and `uv run -m pytest`.
- Collects commits since the last `v*` tag, asks `actions/ai-inference@v2`
  (with prompt at `.github/prompts/release-bump.prompt.yml`) to choose
  `bump: minor|patch` and emit `notes_markdown`.
- Bumps the version with `uv version --bump <bump> --frozen`, commits as
  `chore(release): v<version>`, tags `v<version>`, pushes to `main` with
  `--tags`, creates a GitHub Release, then dispatches `publish.yml`.
- Required permissions: `contents: write`, `models: read`, `actions: write`.

Publish workflow (`.github/workflows/publish.yml`):

- Trigger: `push` of any `v*` tag, or `workflow_dispatch`.
- Steps: setup Python 3.11, `pip install build`, `python -m build`, then
  `pypa/gh-action-pypi-publish@release/v1` with
  `password: ${{ secrets.PYPI_TOKEN }}`.
- Permissions: `contents: read`.

There is also a sibling `publish_token.yml` retained alongside `publish.yml`.

## Allowed values

- `bump` extracted from the AI response is constrained to `minor` or `patch`;
  any other value is forced to `minor` by the `Extract bump + notes` step.
- Version is single-source-of-truth in `pyproject.toml` (`version = "0.4.4"` at
  the time of writing) and updated by `uv version --bump`.

## Known caveats

- `docs/publishing.md` describes PyPI **Trusted Publishing** via OIDC, but the
  current `publish.yml` uses a `PYPI_TOKEN` secret. The two should be
  reconciled when next touched (either migrate the workflow to OIDC or update
  the doc).
- `release.yml` pushes directly to `main` with the bot identity
  `github-actions[bot]`; branch protection must allow this principal or the
  release will fail at the push step.
- Pre-commit hook `teleclaude-docs-check` parses `git diff --cached` with a
  shell `grep`/`xargs` pipeline and exits 1 on match; check the exact regex
  in `.pre-commit-config.yaml` before adjusting.
