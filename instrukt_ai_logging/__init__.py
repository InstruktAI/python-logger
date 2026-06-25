"""InstruktAI logging standard library.

See `README.md` for usage and `docs/design.md` for design intent.
"""

__all__ = [
    "TRACE",
    "InstruktAILogger",
    "InstruktAILoggerProtocol",
    "__version__",
    "configure_logging",
    "get_logger",
    "resolve_log_file",
    "resolve_log_files",
]

try:
    from importlib.metadata import packages_distributions
    from importlib.metadata import version as _pkg_version

    _dists = packages_distributions().get(__name__, [])
    __version__ = _pkg_version(_dists[0]) if _dists else "0.0.0"
except Exception:  # pragma: no cover
    __version__ = "0.0.0"

from instrukt_ai_logging.logging import (
    TRACE,
    InstruktAILogger,
    InstruktAILoggerProtocol,
    configure_logging,
    get_logger,
    resolve_log_file,
    resolve_log_files,
)
