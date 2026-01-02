# Publishing

This repo uses **PyPI Trusted Publishing** via GitHub Actions (OIDC). Releases are handled by the InstruktAI runner in CI: it determines the version, creates the tag, builds `dist/*`, and publishes to PyPI.

## PyPI configuration

Trusted Publishing is configured with:

- Repository: `InstruktAI/python-logger`
- Workflow: `Publish`
- Environment: (none)
