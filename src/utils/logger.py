"""Logging setup: human-readable output on the console, structured
JSON in logs/jarvis.log so logs stay greppable/parseable later."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from pythonjsonlogger import jsonlogger


def setup_logger(name: str, log_level: str = None) -> logging.Logger:
    """Create (or fetch) a logger with console + rotating-file output.

    Example:
        logger = setup_logger(__name__)
        logger.info("Something happened")
    """
    if log_level is None:
        # `os.getenv(KEY, default)` only falls back when the variable is
        # absent — a platform that pre-creates the var blank (Vercel does
        # this when importing a project, scanning .env.example for keys)
        # gets an empty string here instead, which getattr() below would
        # reject. Treating falsy the same as unset covers both cases.
        log_level = os.getenv("LOG_LEVEL") or "INFO"
    if not hasattr(logging, log_level):
        log_level = "INFO"

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))
    logger.handlers = []  # avoid duplicate handlers on repeated setup calls
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    # File logging is best-effort: in read-only environments (some CI
    # runners, some serverless platforms) creating logs/ can fail, and
    # that must never prevent the app from starting.
    try:
        os.makedirs("logs", exist_ok=True)
        file_handler = RotatingFileHandler(
            "logs/jarvis.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(jsonlogger.JsonFormatter())
        logger.addHandler(file_handler)
    except OSError:
        logger.debug("File logging unavailable in this environment; console only.")

    return logger
