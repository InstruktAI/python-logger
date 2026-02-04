"""Install log rotation for InstruktAI logs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _write_file(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"Refusing to overwrite existing file: {path}. Use --force.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_newsyslog(log_root: Path, *, force: bool) -> Path:
    conf_path = Path("/etc/newsyslog.d/instrukt-ai.conf")
    line = f"{log_root}/" + "*/*.log  640  10  100000  *  N\n"
    _write_file(conf_path, line, force=force)
    return conf_path


def _install_logrotate(log_root: Path, *, force: bool) -> Path:
    conf_path = Path("/etc/logrotate.d/instrukt-ai")
    content = f"""{log_root}/*/*.log {{
    size 100M
    rotate 10
    missingok
    notifempty
    copytruncate
}}
"""
    _write_file(conf_path, content, force=force)
    return conf_path


def main() -> None:
    parser = argparse.ArgumentParser(prog="instrukt-ai-log-setup", add_help=True)
    parser.add_argument(
        "--log-root",
        default=os.environ.get("INSTRUKT_AI_LOG_ROOT", "/var/log/instrukt-ai"),
        help="Base log root (default: /var/log/instrukt-ai or INSTRUKT_AI_LOG_ROOT)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing config")
    args = parser.parse_args()

    log_root = Path(args.log_root)
    if sys.platform == "darwin":
        conf = _install_newsyslog(log_root, force=args.force)
    else:
        conf = _install_logrotate(log_root, force=args.force)

    sys.stdout.write(f"installed: {conf}\n")


if __name__ == "__main__":
    main()
