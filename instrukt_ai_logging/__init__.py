"""InstruktAI logging standard library.

See `README.md` for usage and `docs/design.md` for design intent.
"""

__all__ = [
    "__version__",
    "configure_logging",
    "log_kv",
]

__version__ = "0.0.0"

from instrukt_ai_logging.logging import configure_logging, log_kv  # noqa: E402  (intentional re-export)
