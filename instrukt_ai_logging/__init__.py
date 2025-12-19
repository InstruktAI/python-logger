"""InstruktAI logging standard library.

See `README.md` for usage and `docs/design.md` for design intent.
"""

__all__ = [
    "__version__",
    "configure_logging",
    "get_logger",
]

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("instruktai-python-logger")
except Exception:  # pragma: no cover
    __version__ = "0.0.0"

from instrukt_ai_logging.logging import configure_logging, get_logger  # noqa: E402  (intentional re-export)
