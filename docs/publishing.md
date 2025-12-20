# Publishing

This repo is set up for **PyPI Trusted Publishing** via GitHub Actions (OIDC), so we do not need to store a PyPI API token in GitHub secrets.

## How to release

1. Bump `version` in `pyproject.toml`.
2. Create and push a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

3. GitHub Actions workflow `Publish` builds and uploads `dist/*` to PyPI.

## One-time PyPI setup

In the PyPI project settings for `instrukt-ai-logger`:

- Enable **Trusted Publishing**
- Add a publisher for:
  - Repository: `InstruktAI/python-logger`
  - Workflow: `Publish`
  - Environment: (leave blank unless you use one)
