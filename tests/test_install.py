from __future__ import annotations

from pathlib import Path

import pytest
from instrukt_ai_logging.install import _install_logrotate, _install_newsyslog

# Protocol-significant tokens for the rotation configs — named constants per
# software-development/procedure/snapshot-testing (no bare literals in content
# assertions). These are newsyslog field identities, not prose.
_NEWSYSLOG_MODE = "640"
_NEWSYSLOG_COUNT = "5"
_NEWSYSLOG_SIZE_KB = "50000"
_NEWSYSLOG_WHEN = "*"
_NEWSYSLOG_COMPRESS_FLAG = "Z"  # gzip-compress archives
_COMMENT_PREFIX = "#"
_PREEXISTING_CONF = "preexisting"


def test_install_newsyslog_emits_one_line_per_existing_log_file(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    (log_root / "teleclaude").mkdir(parents=True)
    (log_root / "teleclaude" / "teleclaude.log").touch()
    (log_root / "teleclaude" / "cron.log").touch()
    (log_root / "teleclaude" / "docs-watch.log").touch()
    (log_root / "other-app").mkdir()
    (log_root / "other-app" / "other-app.log").touch()
    (log_root / "teleclaude" / "notes.txt").touch()  # ignored: not *.log
    conf_path = tmp_path / "etc" / "newsyslog.d" / "instrukt-ai.conf"

    _install_newsyslog(log_root, force=False, conf_path=conf_path)

    rotated = [
        line.split()[0]
        for line in conf_path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith(_COMMENT_PREFIX)
    ]
    assert rotated == sorted(
        [
            str(log_root / "other-app" / "other-app.log"),
            str(log_root / "teleclaude" / "cron.log"),
            str(log_root / "teleclaude" / "docs-watch.log"),
            str(log_root / "teleclaude" / "teleclaude.log"),
        ]
    )


def test_install_newsyslog_uses_compressing_rotation_defaults(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    (log_root / "app").mkdir(parents=True)
    (log_root / "app" / "app.log").touch()
    conf_path = tmp_path / "newsyslog.conf"

    _install_newsyslog(log_root, force=False, conf_path=conf_path)

    fields = conf_path.read_text(encoding="utf-8").split()
    # path  mode  count  size(KB)  when  flags
    _, mode, count, size_kb, when, flags = fields
    assert mode == _NEWSYSLOG_MODE
    assert count == _NEWSYSLOG_COUNT
    assert size_kb == _NEWSYSLOG_SIZE_KB
    assert when == _NEWSYSLOG_WHEN
    assert _NEWSYSLOG_COMPRESS_FLAG in flags  # gzip-compress archives


def test_install_newsyslog_writes_placeholder_when_no_log_files_exist(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    log_root.mkdir()  # exists but contains no *.log files
    conf_path = tmp_path / "newsyslog.conf"

    _install_newsyslog(log_root, force=False, conf_path=conf_path)

    content = conf_path.read_text(encoding="utf-8")
    assert content.startswith(_COMMENT_PREFIX)
    assert all(line.startswith(_COMMENT_PREFIX) or not line for line in content.splitlines())


def test_install_newsyslog_refuses_overwrite_without_force(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    (log_root / "app").mkdir(parents=True)
    (log_root / "app" / "app.log").touch()
    conf_path = tmp_path / "newsyslog.conf"
    conf_path.write_text(_PREEXISTING_CONF, encoding="utf-8")

    with pytest.raises(SystemExit):
        _install_newsyslog(log_root, force=False, conf_path=conf_path)
    assert conf_path.read_text(encoding="utf-8") == _PREEXISTING_CONF


def test_install_newsyslog_overwrites_with_force(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    (log_root / "app").mkdir(parents=True)
    (log_root / "app" / "app.log").touch()
    conf_path = tmp_path / "newsyslog.conf"
    conf_path.write_text(_PREEXISTING_CONF, encoding="utf-8")

    _install_newsyslog(log_root, force=True, conf_path=conf_path)
    assert conf_path.read_text(encoding="utf-8") != _PREEXISTING_CONF


def test_install_logrotate_writes_glob_block_with_compressing_defaults(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    log_root.mkdir()
    conf_path = tmp_path / "logrotate.conf"

    _install_logrotate(log_root, force=False, conf_path=conf_path)

    content = conf_path.read_text(encoding="utf-8")
    # logrotate handles multi-level globs natively, unlike macOS newsyslog.
    assert f"{log_root}/*/*.log" in content
    # Protocol-significant directives — these are logrotate keywords, not prose.
    for directive in (
        "size 50M",
        "rotate 5",
        "compress",
        "delaycompress",
        "missingok",
        "copytruncate",
    ):
        assert directive in content


def test_install_logrotate_refuses_overwrite_without_force(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    log_root.mkdir()
    conf_path = tmp_path / "logrotate.conf"
    conf_path.write_text(_PREEXISTING_CONF, encoding="utf-8")

    with pytest.raises(SystemExit):
        _install_logrotate(log_root, force=False, conf_path=conf_path)
    assert conf_path.read_text(encoding="utf-8") == _PREEXISTING_CONF
