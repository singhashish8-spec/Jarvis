"""Custom exception types, so error handling is consistent and each
error carries the HTTP status code it should produce."""

from typing import Any, Dict, Tuple


class APIError(Exception):
    """Base error for anything the API deliberately rejects or fails on."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(APIError):
    """Request body/params failed validation."""

    def __init__(self, message: str):
        super().__init__(f"Validation error: {message}", 400)


class AuthenticationError(APIError):
    """Credentials missing or invalid."""

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, 401)


class DatabaseError(APIError):
    """Supabase call failed."""

    def __init__(self, message: str = "Database error"):
        super().__init__(message, 503)


class StorageError(APIError):
    """R2 call failed."""

    def __init__(self, message: str = "Storage error"):
        super().__init__(message, 503)


class AgentError(APIError):
    """An agent (Brainstorm, Coder, ...) failed to produce a result."""

    def __init__(self, message: str = "Agent error"):
        super().__init__(message, 500)


class RateLimitError(APIError):
    """Too many requests in a short window."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, 429)


def handle_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Convert any exception into a (json_body, status_code) pair
    that a Flask route can return directly."""
    if isinstance(error, APIError):
        return (
            {
                "error": error.__class__.__name__,
                "message": error.message,
                "status": error.status_code,
            },
            error.status_code,
        )

    return (
        {
            "error": "InternalError",
            "message": "An unexpected error occurred",
            "status": 500,
        },
        500,
    )
