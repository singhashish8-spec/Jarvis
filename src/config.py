"""Configuration management.

Settings come from environment variables (see .env.example), never
hardcoded — so real credentials never end up committed to Git.
"""

import os
from datetime import timedelta


class Config:
    """Base configuration shared by all environments."""

    DEBUG = False
    TESTING = False
    JSON_SORT_KEYS = False

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")
    REPLICATE_TIMEOUT = 300  # seconds

    # Replicate has no API for account balance, so this is a budget the
    # user sets manually (matching what they've actually loaded at
    # replicate.com/account/billing) for the dashboard to track estimated
    # spend against. None (unset) means "don't show a limit".
    REPLICATE_CREDIT_LIMIT_USD = (
        float(os.getenv("REPLICATE_CREDIT_LIMIT_USD"))
        if os.getenv("REPLICATE_CREDIT_LIMIT_USD")
        else None
    )

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    R2_ACCOUNT_ID = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID")
    R2_ACCESS_KEY = os.getenv("CLOUDFLARE_R2_ACCESS_KEY")
    R2_SECRET_KEY = os.getenv("CLOUDFLARE_R2_SECRET_KEY")
    R2_BUCKET_NAME = os.getenv("CLOUDFLARE_R2_BUCKET_NAME", "jarvis-data")
    R2_ENDPOINT = os.getenv("CLOUDFLARE_R2_ENDPOINT")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    FEATURE_BRAINSTORM_AGENT = os.getenv("FEATURE_BRAINSTORM_AGENT", "True") == "True"
    FEATURE_CODER_AGENT = os.getenv("FEATURE_CODER_AGENT", "False") == "True"
    FEATURE_TEST_AGENT = os.getenv("FEATURE_TEST_AGENT", "False") == "True"


class DevelopmentConfig(Config):
    """Local machine configuration."""

    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Vercel/production configuration."""

    DEBUG = False


class TestingConfig(Config):
    """Configuration used while running pytest."""

    TESTING = True
    DEBUG = True
    SESSION_COOKIE_SECURE = False


def _select_config() -> Config:
    env = os.getenv("ENV", "development").lower()
    if env == "production":
        return ProductionConfig()
    if env == "testing":
        return TestingConfig()
    return DevelopmentConfig()


config = _select_config()


def validate_config() -> None:
    """Raise if a required credential is missing.

    Called from setup/verify scripts, not on every import, so the app can
    still boot (and show a clear error) before .env is fully filled in.
    """
    required = ["REPLICATE_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "R2_ACCOUNT_ID"]
    missing = [name for name in required if not getattr(config, name, None)]
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
