from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging.handlers import WatchedFileHandler
from pathlib import Path
from typing import Any


def _normalize_env_prefix(name: str) -> str:
    # TELECLAUDE, MY_APP, etc.
    raw = name.strip().upper()
    if not raw:
        raise ValueError("name must be non-empty")
    raw = re.sub(r"[^A-Z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        raise ValueError("name did not produce a valid env prefix")
    return raw


def _normalize_app_name(name: str) -> str:
    # teleclaude, my-app, etc.
    raw = name.strip().lower()
    if not raw:
        raise ValueError("name must be non-empty")
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    if not raw:
        raise ValueError("name did not produce a valid app name")
    return raw


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


_SAFE_BARE_VALUE = re.compile(r"^[A-Za-z0-9._/:+-]+$")
_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

# Keep this small and high-signal; expand only with strong justification.
_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Telegram bot token in API URLs: https://api.telegram.org/bot<token>/...
    (re.compile(r"(api\\.telegram\\.org/bot)([^/\\s]+)"), r"\\1<REDACTED>"),
    # Generic Bearer token
    (re.compile(r"\\bBearer\\s+[^\\s]+"), "Bearer <REDACTED>"),
    # Common OpenAI-style key prefix (avoid leaking)
    (re.compile(r"\\bsk-[A-Za-z0-9]{10,}\\b"), "sk-<REDACTED>"),
]


def _redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "…(truncated)"
    return text


def _escape_quotes(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _format_logfmt_value(value: object, *, max_chars: int) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)

    text = _redact_text(str(value))
    text = _truncate_text(text, max_chars=max_chars)

    if _SAFE_BARE_VALUE.fullmatch(text):
        return text
    return f'"{_escape_quotes(text)}"'


def _format_logfmt_string(text: str, *, max_chars: int, force_quote: bool) -> str:
    redacted = _redact_text(text)
    redacted = _truncate_text(redacted, max_chars=max_chars)
    if not force_quote and _SAFE_BARE_VALUE.fullmatch(redacted):
        return redacted
    return f'"{_escape_quotes(redacted)}"'


class LogfmtFormatter(UtcMillisFormatter):
    """Single-line logfmt-ish formatter.

    Always emits key/value pairs with at least:
      level=..., logger=..., msg="..."

    Optional additional pairs can be attached via `extra={"kv": {...}}`.
    """

    def __init__(self, max_message_chars: int) -> None:
        super().__init__(datefmt=None)
        self.max_message_chars = max_message_chars

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record)
        try:
            message = record.getMessage()
        except Exception:
            message = "<unprintable>"

        parts = [
            ts,
            f"level={_format_logfmt_value(record.levelname, max_chars=self.max_message_chars)}",
            f"logger={_format_logfmt_value(record.name, max_chars=self.max_message_chars)}",
            f"msg={_format_logfmt_string(str(message), max_chars=self.max_message_chars, force_quote=True)}",
        ]

        kv: object = getattr(record, "kv", None)
        if isinstance(kv, dict):
            for key in sorted(kv.keys(), key=lambda x: str(x)):
                if key == "msg":
                    continue
                if not isinstance(key, str):
                    continue
                if not _SAFE_KEY.fullmatch(key):
                    continue
                parts.append(
                    f"{key}={_format_logfmt_value(kv[key], max_chars=self.max_message_chars)}"
                )

        if record.exc_info:
            try:
                exc_text = self.formatException(record.exc_info).replace("\n", "\\n")
            except Exception:
                exc_text = "<exception>"
            parts.append(f"exc={_format_logfmt_value(exc_text, max_chars=self.max_message_chars)}")

        return " ".join(parts)


class InstruktLogger(logging.Logger):
    """Logger that accepts arbitrary `**kv` fields.

    This lets callers use normal logger methods with named key/value pairs:
      logging.getLogger("...").info("event_name", job_id=..., user_id=...)

    All `**kv` values are serialized to text by the formatter.
    """

    def _log_with_kv(self, level: int, msg: object, args: tuple[object, ...], **kwargs: Any) -> None:
        exc_info = kwargs.pop("exc_info", None)
        stack_info = kwargs.pop("stack_info", False)
        stacklevel = kwargs.pop("stacklevel", 1)
        extra = kwargs.pop("extra", None)

        # Remaining kwargs are treated as `kv`.
        kv: dict[str, object] = {k: v for k, v in kwargs.items() if _SAFE_KEY.fullmatch(k)}

        merged_extra: dict[str, object] = {}
        if isinstance(extra, dict):
            merged_extra.update(extra)

        existing_kv = merged_extra.get("kv")
        if isinstance(existing_kv, dict):
            merged_extra["kv"] = {**existing_kv, **kv}
        else:
            merged_extra["kv"] = kv

        super()._log(
            level,
            msg,
            args,
            exc_info=exc_info,
            extra=merged_extra,
            stack_info=stack_info,
            stacklevel=stacklevel,
        )

    def debug(self, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        if self.isEnabledFor(logging.DEBUG):
            self._log_with_kv(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        if self.isEnabledFor(logging.INFO):
            self._log_with_kv(logging.INFO, msg, args, **kwargs)

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        if self.isEnabledFor(logging.WARNING):
            self._log_with_kv(logging.WARNING, msg, args, **kwargs)

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        if self.isEnabledFor(logging.ERROR):
            self._log_with_kv(logging.ERROR, msg, args, **kwargs)

    def critical(self, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        if self.isEnabledFor(logging.CRITICAL):
            self._log_with_kv(logging.CRITICAL, msg, args, **kwargs)

    def exception(self, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        kwargs.setdefault("exc_info", True)
        if self.isEnabledFor(logging.ERROR):
            self._log_with_kv(logging.ERROR, msg, args, **kwargs)

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:  # type: ignore[override]
        if not isinstance(level, int):
            raise TypeError("level must be an int")
        if self.isEnabledFor(level):
            self._log_with_kv(level, msg, args, **kwargs)


def get_logger(name: str) -> logging.Logger:
    """Compatibility helper (returns a normal logger, but with `**kv` support after configuration)."""
    return logging.getLogger(name)


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
    app_logger_prefix: str,
    name: str | None = None,
    env_prefix: str | None = None,
    app_name: str | None = None,
    log_filename: str | None = None,
    max_message_chars: int = 4000,
) -> Path:
    """Configure logging according to the InstruktAI contract.

    Returns the resolved log file path in use.
    """
    if name is not None:
        if env_prefix is not None or app_name is not None:
            raise ValueError("Pass either name= OR env_prefix/app_name (not both)")
        env_prefix = _normalize_env_prefix(name)
        app_name = _normalize_app_name(name)

    if env_prefix is None or app_name is None:
        raise ValueError("Missing required config: name= OR both env_prefix= and app_name=")

    contract = LoggingContract(
        env_prefix=env_prefix,
        app_logger_prefix=app_logger_prefix,
        app_name=app_name,
    )

    # Ensure all loggers accept arbitrary `**kv` (no wrapper at call sites).
    logging.setLoggerClass(InstruktLogger)
    for obj in logging.root.manager.loggerDict.values():
        if isinstance(obj, logging.Logger) and not isinstance(obj, InstruktLogger):
            obj.__class__ = InstruktLogger

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

    formatter = LogfmtFormatter(max_message_chars=max_message_chars)

    handler = WatchedFileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(formatter)
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
