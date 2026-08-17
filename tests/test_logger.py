"""Tests for setup_logger, covering a real bug found in production:
a platform (Vercel) pre-created LOG_LEVEL as an empty string rather
than leaving it unset, which crashed getattr(logging, '') on every
request."""

import logging

from src.utils.logger import setup_logger


def test_setup_logger_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logger = setup_logger("test.default")
    assert logger.level == logging.INFO


def test_setup_logger_handles_empty_string_env_var(monkeypatch):
    """Reproduces the exact production crash: LOG_LEVEL="" (present but
    blank) must fall back to INFO instead of raising AttributeError."""
    monkeypatch.setenv("LOG_LEVEL", "")
    logger = setup_logger("test.empty")
    assert logger.level == logging.INFO


def test_setup_logger_handles_invalid_level_name(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_REAL_LEVEL")
    logger = setup_logger("test.invalid")
    assert logger.level == logging.INFO


def test_setup_logger_respects_valid_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logger = setup_logger("test.debug")
    assert logger.level == logging.DEBUG
