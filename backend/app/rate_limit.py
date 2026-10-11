"""Rate limiting for authentication endpoints.

Redis is used when configured so limits are shared across app workers.
Without Redis, the limiter uses in-process memory (suitable for local development).
"""
import ipaddress

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .config import get_settings


def get_client_address(request: Request) -> str:
    """Resolve the rate-limit key from a trusted edge header only when configured."""
    settings = get_settings()
    if settings.TRUST_CF_CONNECTING_IP:
        forwarded_ip = request.headers.get("cf-connecting-ip", "").strip()
        try:
            return ipaddress.ip_address(forwarded_ip).compressed
        except ValueError:
            # Never trust malformed values; fallback is safe, but behind Render it
            # can temporarily put requests into the shared proxy-IP bucket.
            pass
    return get_remote_address(request)


_settings = get_settings()
limiter = Limiter(
    key_func=get_client_address,
    storage_uri=_settings.REDIS_URL or "memory://",
    in_memory_fallback_enabled=bool(_settings.REDIS_URL),
)
