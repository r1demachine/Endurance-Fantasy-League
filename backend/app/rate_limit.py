"""Rate limiting for authentication endpoints.

Redis is used when configured so limits are shared across app workers.
Without Redis, the limiter uses in-process memory (suitable for local development).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings


_settings = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.REDIS_URL or "memory://",
    in_memory_fallback_enabled=bool(_settings.REDIS_URL),
)
