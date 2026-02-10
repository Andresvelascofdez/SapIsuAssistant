"""
Shared error messages per PRACTICES.md section 8.

User-visible errors must be clear and actionable.
"""


class AppErrors:
    """Centralized actionable error messages."""

    QDRANT_UNREACHABLE = (
        "Qdrant is not reachable. Start docker-compose and retry."
    )

    OPENAI_AUTH_FAILED = (
        "OpenAI authentication failed. Check your API key in Settings."
    )

    OPENAI_RATE_LIMIT = (
        "OpenAI rate limit exceeded. Wait a moment and try again."
    )

    NO_CLIENT_SELECTED = (
        "No client selected. Choose a client from the top bar."
    )

    NO_KB_DATABASE = (
        "No knowledge base found for this scope. Ingest content first."
    )

    SYNTHESIS_FAILED = (
        "Synthesis failed after retries. Check logs and try again."
    )

    EMPTY_INPUT = (
        "Input is empty. Provide text or select a file."
    )


def format_openai_error(error: Exception) -> str:
    """Format OpenAI API error with request_id if available."""
    from openai import (
        AuthenticationError,
        RateLimitError,
        APIConnectionError,
        APIStatusError,
    )

    if isinstance(error, AuthenticationError):
        return AppErrors.OPENAI_AUTH_FAILED

    if isinstance(error, RateLimitError):
        return AppErrors.OPENAI_RATE_LIMIT

    if isinstance(error, APIConnectionError):
        return f"OpenAI connection error: {error}"

    if isinstance(error, APIStatusError):
        request_id = getattr(error, "request_id", None) or "N/A"
        return f"OpenAI error (request_id={request_id}): {error.message}"

    return f"OpenAI error: {error}"


def format_qdrant_error(error: Exception) -> str:
    """Format Qdrant error as actionable message."""
    error_str = str(error).lower()
    if "connect" in error_str or "refused" in error_str or "unreachable" in error_str:
        return AppErrors.QDRANT_UNREACHABLE
    return f"Qdrant error: {error}"
