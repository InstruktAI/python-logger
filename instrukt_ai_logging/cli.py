from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterator

from instrukt_ai_logging.logging import (
    iter_recent_log_lines,
    parse_since,
    resolve_log_file,
)


def iter_follow_lines(
    log_file: Path,
    *,
    poll_interval_s: float = 0.25,
    start_at_end: bool = True,
    max_lines: int | None = None,
    max_seconds: float | None = None,
) -> Iterator[str]:
    """Yield new lines appended to `log_file`, similar to `tail -f`.

    - Detects rotation (inode change) and truncation.
    - Waits for file creation if it doesn't exist yet.
    - `max_lines`/`max_seconds` are mainly for tests.
    """
    deadline = None if max_seconds is None else (time.monotonic() + max_seconds)
    emitted = 0

    f = None
    inode = None
    start_at_end_for_next_open = start_at_end

    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                return

            if f is None:
                try:
                    f = log_file.open("r", encoding="utf-8", errors="replace")
                except FileNotFoundError:
                    time.sleep(poll_interval_s)
                    continue

                try:
                    inode = os.fstat(f.fileno()).st_ino
                except OSError:
                    inode = None

                if start_at_end_for_next_open:
                    f.seek(0, os.SEEK_END)
                else:
                    f.seek(0, os.SEEK_SET)

                # Only the first open may start at end; after rotation we read from start.
                start_at_end_for_next_open = False

            line = f.readline()
            if line:
                yield line
                emitted += 1
                if max_lines is not None and emitted >= max_lines:
                    return
                continue

            # No new data: detect rotation/truncation and wait.
            try:
                st = log_file.stat()
            except FileNotFoundError:
                f.close()
                f = None
                inode = None
                time.sleep(poll_interval_s)
                continue

            if inode is not None and getattr(st, "st_ino", None) is not None and st.st_ino != inode:
                f.close()
                f = None
                inode = None
                continue

            if f.tell() > st.st_size:
                f.seek(0, os.SEEK_SET)

            time.sleep(poll_interval_s)
    finally:
        if f is not None:
            try:
                f.close()
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(prog="instrukt-ai-logs", add_help=True)
    parser.add_argument("app", help="App/service name (folder and filename stem)")
    parser.add_argument(
        "--since", default="10m", help="Time window (e.g. 10m, 2h, 1d). Default: 10m"
    )
    parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow the log (tail -f style) after printing the --since window",
    )
    parser.add_argument("--grep", default="", help="Regex to filter lines (optional)")
    args = parser.parse_args()

    try:
        since = parse_since(args.since)
    except ValueError as e:
        raise SystemExit(str(e)) from e

    log_file = resolve_log_file(args.app)
    if not log_file.exists():
        raise SystemExit(f"Log file not found: {log_file}")

    pattern = re.compile(args.grep) if args.grep else None
    for line in iter_recent_log_lines(log_file, since):
        if pattern and not pattern.search(line):
            continue
        sys.stdout.write(line)

    if not args.follow:
        return

    sys.stdout.flush()
    try:
        for line in iter_follow_lines(log_file, start_at_end=True):
            if pattern and not pattern.search(line):
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
    except KeyboardInterrupt:
        return
