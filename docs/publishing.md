# Publishing

This repo uses **PyPI Trusted Publishing** via GitHub Actions (OIDC). Releases are handled in CI. On every push to `main` the `Release (Auto)` workflow runs lint and tests, then a release inspector (`anthropics/claude-code-action`, instructions in `.github/prompts/release-inspector.md`) reads the diff since the last tag against the library's public contract and returns the semver bump and the release notes. The workflow then bumps the version, creates the tag and GitHub Release, and dispatches the `Publish` workflow, which builds `dist/*` and publishes to PyPI.

The inspector authenticates with the `CLAUDE_CODE_OAUTH_TOKEN` repository secret.

## PyPI configuration

Trusted Publishing is configured with:

- Repository: `InstruktAI/python-logger`
- Workflow: `Publish`
- Environment: (none)
