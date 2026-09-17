"""
Centralized logging setup.

Two log files are produced:
  - logs/pipeline.log   -> everything (DEBUG and above), for tracing each step
  - logs/failures.log   -> ERROR and above only, so failures are easy to find
                            without digging through the full trace

Usage in any module:
    from logger_config import get_logger
    logger = get_logger(__name__)
    logger.info("something happened")
    logger.error("something failed", exc_info=True)
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.getenv("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

MAIN_LOG_FILE = os.path.join(LOG_DIR, "pipeline.log")
FAILURE_LOG_FILE = os.path.join(LOG_DIR, "failures.log")

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if get_logger() is called multiple times
    # for the same module (e.g. on reimport).
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console: INFO and above, for live visibility while running
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Main file: everything, full trace of each step
    main_file_handler = RotatingFileHandler(
        MAIN_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    main_file_handler.setLevel(logging.DEBUG)
    main_file_handler.setFormatter(formatter)

    # Failure file: ERROR and above only
    failure_file_handler = RotatingFileHandler(
        FAILURE_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    failure_file_handler.setLevel(logging.ERROR)
    failure_file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(main_file_handler)
    logger.addHandler(failure_file_handler)

    logger.propagate = False
    return logger
