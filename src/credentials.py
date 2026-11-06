"""The Gemini API key for the job being processed.

A job may carry the user's own key (`api_key` in the message, from the UI's API key field). It is set
here for the duration of that job, so every Gemini call in the job uses it instead of the process's
GOOGLE_API_KEY. A context variable keeps concurrent jobs (separate threads) from seeing each other's key.
The key is never logged or returned in results.
"""
import contextvars
from contextlib import contextmanager
from typing import Optional

_api_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("gemini_api_key", default=None)

# Gemini's wording when it refuses a key (400 API_KEY_INVALID / 403 for a revoked or restricted key).
INVALID_KEY_MARKERS = ("API_KEY_INVALID", "API key not valid", "API key expired", "API_KEY_SERVICE_BLOCKED")


class InvalidApiKey(ValueError):
    pass


@contextmanager
def use_api_key(key: Optional[str]):
    token = _api_key.set(key or None)
    try:
        yield
    finally:
        _api_key.reset(token)


def llm_kwargs() -> dict:
    """Extra ChatGoogleGenerativeAI arguments: the job's own key, if it has one."""
    key = _api_key.get()
    return {"google_api_key": key} if key else {}


def check_rejected_key(error: Exception):
    """Turn Gemini's 'bad API key' error into a clear, non-retryable one."""
    if any(marker in str(error) for marker in INVALID_KEY_MARKERS):
        own = "your" if _api_key.get() else "the server's"
        raise InvalidApiKey(f"Gemini rejected {own} API key. Check it at https://aistudio.google.com/apikey") from None
