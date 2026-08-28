"""Centralised logging configuration.

Logs are written as "pretty" key=value lines to keep them readable in Docker
logs while staying machine-parseable enough for simple aggregation.
"""

from __future__ import annotations

import logging
import sys

_LOGGER_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(level: str = "INFO") -> None:
    """Apply the application-wide logging configuration once per process."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOGGER_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)

    # Keep noisy third-party loggers at a sane level.
    for noisy_logger in ("uvicorn.access", "botocore", "boto3", "s3transfer", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger for *name*."""
    return logging.getLogger(name)
