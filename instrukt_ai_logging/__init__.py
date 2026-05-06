"""InstruktAI logging standard library.

See `README.md` for usage and `docs/design.md` for design intent.
"""

__all__ = [
    "__version__",
    "configure_logging",
    "get_logger",
    "InstruktAILogger",
    "InstruktAILoggerProtocol",
    "resolve_log_file",
    "resolve_log_files",
    "TRACE",
]

try:
    from importlib.metadata import packages_distributions, version as _pkg_version

    _dists = packages_distributions().get(__name__, [])
    __version__ = _pkg_version(_dists[0]) if _dists else "0.0.0"
except Exception:  # pragma: no cover
    __version__ = "0.0.0"

from instrukt_ai_logging.logging import (  # noqa: E402  (intentional re-export)
    configure_logging,
    get_logger,
    InstruktAILogger,
    InstruktAILoggerProtocol,
    resolve_log_file,
    resolve_log_files,
    TRACE,
)
