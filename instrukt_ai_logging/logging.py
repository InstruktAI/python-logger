from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging.handlers import WatchedFileHandler
from pathlib import Path


def _level_name_to_int(level_name: str, default: int) -> int:
    name = level_name.strip().upper()
    if not name:
        return default
    candidate: object = getattr(logging, name, None)
    if isinstance(candidate, int):
        return candidate
    return default


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class UtcMillisFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z"


class RedactAndTruncateFilter(logging.Filter):
    def __init__(self, max_chars: int) -> None:
        super().__init__()
        self.max_chars = max_chars

        # Keep this small and high-signal; expand only with strong justification.
        self._patterns: list[tuple[re.Pattern[str], str]] = [
            # Telegram bot token in API URLs: https://api.telegram.org/bot<token>/...
            (re.compile(r"(api\\.telegram\\.org/bot)([^/\\s]+)"), r"\\1<REDACTED>"),
            # Generic Bearer token
            (re.compile(r"\\bBearer\\s+[^\\s]+"), "Bearer <REDACTED>"),
            # Common OpenAI-style key prefix (avoid leaking)
            (re.compile(r"\\bsk-[A-Za-z0-9]{10,}\\b"), "sk-<REDACTED>"),
        ]

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            message = record.getMessage()
        except Exception:
            return True

        redacted = message
        for pattern, replacement in self._patterns:
            redacted = pattern.sub(replacement, redacted)

        if self.max_chars > 0 and len(redacted) > self.max_chars:
            redacted = redacted[: self.max_chars] + "…(truncated)"

        if redacted != message:
            record.msg = redacted
            record.args = ()

        return True


class _ThirdPartySelectorFilter(logging.Filter):
    """Enforce third-party spotlight semantics on a handler.

    - Always allow records from `app_logger_prefix`.
    - For non-app loggers:
      - If `spotlight_prefixes` is empty: allow (level gating happens via logger levels).
      - If `spotlight_prefixes` is set: only allow records whose logger name starts with one of them.
    """

    def __init__(self, app_logger_prefix: str, spotlight_prefixes: tuple[str, ...]) -> None:
        super().__init__()
        self.app_logger_prefix = app_logger_prefix
        self.spotlight_prefixes = spotlight_prefixes

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        name = record.name
        if name == self.app_logger_prefix or name.startswith(self.app_logger_prefix + "."):
            return True
        if not self.spotlight_prefixes:
            return True
        return any(name == p or name.startswith(p + ".") for p in self.spotlight_prefixes)


@dataclass(frozen=True)
class LoggingContract:
    env_prefix: str
    app_logger_prefix: str
    app_name: str

    @property
    def env_log_level(self) -> str:
        return f"{self.env_prefix}_LOG_LEVEL"

    @property
    def env_third_party_level(self) -> str:
        return f"{self.env_prefix}_THIRD_PARTY_LOG_LEVEL"

    @property
    def env_third_party_loggers(self) -> str:
        return f"{self.env_prefix}_THIRD_PARTY_LOGGERS"


def _resolve_log_root(app_name: str) -> Path:
    override = os.getenv("INSTRUKT_AI_LOG_ROOT")
    if override:
        return Path(override).expanduser()
    return Path("/var/log/instrukt-ai") / app_name


def _fallback_log_root(app_name: str) -> Path:
    # Deterministic fallback: repo-local ./logs if available, else /tmp.
    candidate = Path.cwd() / "logs"
    if candidate.exists() or candidate.parent.exists():
        return candidate
    return Path("/tmp") / "instrukt-ai" / app_name


def _ensure_log_dir(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)


def configure_logging(
    *,
    env_prefix: str,
    app_logger_prefix: str,
    app_name: str,
    log_filename: str | None = None,
    max_message_chars: int = 4000,
) -> Path:
    """Configure logging according to the InstruktAI contract.

    Returns the resolved log file path in use.
    """
    contract = LoggingContract(
        env_prefix=env_prefix,
        app_logger_prefix=app_logger_prefix,
        app_name=app_name,
    )

    our_level_name = (os.getenv(contract.env_log_level) or "INFO").upper()
    third_party_level_name = (os.getenv(contract.env_third_party_level) or "WARNING").upper()
    spotlight = _parse_csv(os.getenv(contract.env_third_party_loggers, ""))

    our_level = _level_name_to_int(our_level_name, logging.INFO)
    third_party_level = _level_name_to_int(third_party_level_name, logging.WARNING)

    # Root logger governs all loggers that don't explicitly set a level.
    root_level = third_party_level if not spotlight else logging.WARNING

    log_dir = _resolve_log_root(app_name)
    try:
        _ensure_log_dir(log_dir)
    except (PermissionError, OSError):
        log_dir = _fallback_log_root(app_name)
        _ensure_log_dir(log_dir)

    log_file = log_dir / (log_filename or f"{app_name}.log")

    formatter = UtcMillisFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    handler = WatchedFileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(formatter)
    handler.addFilter(RedactAndTruncateFilter(max_chars=max_message_chars))
    handler.addFilter(
        _ThirdPartySelectorFilter(
            app_logger_prefix=app_logger_prefix, spotlight_prefixes=tuple(spotlight)
        )
    )

    # Configure root.
    logging.root.handlers = [handler]
    logging.root.setLevel(root_level)

    # Configure our logs.
    logging.getLogger(app_logger_prefix).setLevel(our_level)

    # Configure spotlight third-party prefixes (only affects non-app loggers).
    for prefix in spotlight:
        if prefix == app_logger_prefix or prefix.startswith(app_logger_prefix + "."):
            continue
        logging.getLogger(prefix).setLevel(third_party_level)

    # Optional console output for interactive runs only.
    if sys.stdout.isatty():  # type: ignore[misc]
        console = logging.StreamHandler()
        console.setLevel(logging.NOTSET)
        console.setFormatter(formatter)
        console.addFilter(RedactAndTruncateFilter(max_chars=max_message_chars))
        console.addFilter(
            _ThirdPartySelectorFilter(
                app_logger_prefix=app_logger_prefix,
                spotlight_prefixes=tuple(spotlight),
            )
        )
        logging.root.addHandler(console)

    return log_file


def parse_since(value: str) -> timedelta:
    """Parse durations like '10m', '2h', '1d', '30s'."""
    raw = value.strip().lower()
    if not raw:
        raise ValueError("Empty duration")
    unit = raw[-1]
    number = raw[:-1]
    if not number.isdigit():
        raise ValueError(f"Invalid duration: {value}")
    n = int(number)
    if unit == "s":
        return timedelta(seconds=n)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    raise ValueError(f"Invalid duration unit: {unit}")


def parse_log_timestamp(line: str) -> datetime | None:
    """Parse the timestamp at the start of a standard log line.

    Expected: YYYY-MM-DDTHH:MM:SS.mmmZ ...
    """
    token = line.split(" ", 1)[0].strip()
    if not token.endswith("Z"):
        return None
    try:
        # Python doesn't accept 'Z' directly in fromisoformat.
        return datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError:
        return None


def iter_recent_log_lines(log_file: Path, since: timedelta) -> list[str]:
    """Return log lines newer than now-`since`, reading rotated siblings when present."""
    cutoff = _now_utc() - since

    candidates = sorted(
        [
            p
            for p in log_file.parent.glob(log_file.name + "*")
            if p.is_file() and not p.name.endswith(".gz")
        ],
        key=lambda p: p.stat().st_mtime,
    )

    lines: list[str] = []
    for path in candidates:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = parse_log_timestamp(line)
                    if ts is None:
                        continue
                    if ts >= cutoff:
                        lines.append(line)
        except FileNotFoundError:
            continue

    return lines
