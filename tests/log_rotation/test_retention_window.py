from __future__ import annotations

import sys

import pytest
from instrukt_ai_logging import install
from syrupy.assertion import SnapshotAssertion

# Archive-depth contract: project/spec/feature/log_rotation/retention-window#archive-depth.
_ARCHIVE_DEPTH = 30
_SEGMENT_SIZE_KB = 50_000
_SEGMENT_SIZE_MB = 50


@pytest.mark.spec("project/spec/feature/log_rotation/retention-window", "UC-RW1")
@pytest.mark.functional
def test_runtime_install_writes_newsyslog_archive_depth(
    monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    install.main()

    conf_content = install._newsyslog_conf_path().read_text(encoding="utf-8")
    _, _, count, size_kb, _, flags = conf_content.split()
    assert int(count) == _ARCHIVE_DEPTH
    assert int(size_kb) == _SEGMENT_SIZE_KB
    assert flags == snapshot


@pytest.mark.spec("project/spec/feature/log_rotation/retention-window", "UC-RW2")
@pytest.mark.functional
def test_runtime_install_writes_logrotate_matching_newsyslog_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    install.main()

    directives = {
        parts[0]: parts[1]
        for line in install._logrotate_conf_path().read_text(encoding="utf-8").splitlines()
        if (parts := line.strip().split(maxsplit=1)) and len(parts) == 2
    }
    assert int(directives["rotate"]) == _ARCHIVE_DEPTH
    assert int(directives["size"].removesuffix("M")) == _SEGMENT_SIZE_MB
