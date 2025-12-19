from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from instrukt_ai_logging.logging import (
    _fallback_log_root,
    _resolve_log_root,
    iter_recent_log_lines,
    parse_since,
)


def _resolve_log_file(app: str) -> Path:
    primary_dir = _resolve_log_root(app)
    primary_file = primary_dir / f"{app}.log"
    if primary_file.exists():
        return primary_file

    fallback_dir = _fallback_log_root(app)
    fallback_file = fallback_dir / f"{app}.log"
    if fallback_file.exists():
        return fallback_file

    return primary_file


def main() -> None:
    parser = argparse.ArgumentParser(prog="instrukt-ai-logs", add_help=True)
    parser.add_argument("app", help="App/service name (folder and filename stem)")
    parser.add_argument(
        "--since", default="10m", help="Time window (e.g. 10m, 2h, 1d). Default: 10m"
    )
    parser.add_argument("--grep", default="", help="Regex to filter lines (optional)")
    args = parser.parse_args()

    try:
        since = parse_since(args.since)
    except ValueError as e:
        raise SystemExit(str(e)) from e

    log_file = _resolve_log_file(args.app)
    if not log_file.exists():
        raise SystemExit(f"Log file not found: {log_file}")

    pattern = re.compile(args.grep) if args.grep else None
    for line in iter_recent_log_lines(log_file, since):
        if pattern and not pattern.search(line):
            continue
        sys.stdout.write(line)
