from __future__ import annotations

import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from instrukt_ai_logging.cli import iter_follow_lines


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)
        f.flush()


def test_iter_follow_lines_yields_appended_lines_only():
    with TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "app.log"
        log_file.write_text("old\n", encoding="utf-8")

        got: list[str] = []

        def _reader():
            got.extend(
                list(
                    iter_follow_lines(
                        log_file,
                        poll_interval_s=0.01,
                        start_at_end=True,
                        max_lines=2,
                        max_seconds=2,
                    )
                )
            )

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        # Give the reader time to open+seek to end.
        time.sleep(0.05)
        _append(log_file, "new1\n")
        _append(log_file, "new2\n")

        t.join(timeout=3)
        assert got == ["new1\n", "new2\n"]

