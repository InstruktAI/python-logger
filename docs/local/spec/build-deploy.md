---
id: "local/projects/python-logger/spec/build-deploy"
type: "spec"
scope: "project"
description: "Build and release pipeline for instruktai-python-logger: setuptools build, inspector-decided semver bump on push to main, PyPI publish on tag push."
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
- Two jobs. `inspect` runs with read-only repository permission and does not
  persist the checkout credential into the workspace, because it processes
  commit-derived text. `release` needs `inspect` and holds the write
  permissions (`contents: write`, `actions: write`).
- `inspect` collects the commits since the last `v*` tag and runs the release
  inspector (`anthropics/claude-code-action`, authenticated with the
  `CLAUDE_CODE_OAUTH_TOKEN` secret, instructions in
  `.github/prompts/release-inspector.md`). The inspector reads the real diff
  against the library's public contract and returns `bump`, `breaking`,
  `rationale` and `notes_markdown` as structured output.
- `inspect` validates the whole result (not only `bump`) and stops the run on
  any violation, then hands `release` the validated bump as a job output and
  the notes as the `release-notes` artifact.
- `release` has a skip step that bails out if the head commit subject matches
  `chore(release):*`, then sets up Python and `uv`, installs the dev group,
  and runs `ruff check` and `pytest`.
- `release` bumps the version with `uv version --bump <bump> --frozen`,
  commits as `chore(release): v<version>`, tags `v<version>`, pushes to `main`
  with `--tags`, creates a GitHub Release from the notes artifact, then
  dispatches `publish.yml`.

Publish workflow (`.github/workflows/publish.yml`):

- Trigger: `push` of any `v*` tag, or `workflow_dispatch`.
- Steps: setup Python 3.11, `pip install build`, `python -m build`, then
  `pypa/gh-action-pypi-publish@release/v1` with
  `password: ${{ secrets.PYPI_TOKEN }}`.
- Permissions: `contents: read`.

There is also a sibling `publish_token.yml` retained alongside `publish.yml`.

## Allowed values

- `bump` from the inspector is constrained to `minor` or `patch`; any other
  value, or a result missing a required field, fails the `inspect` job and
  nothing is released.
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
