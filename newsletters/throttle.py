from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def is_limited(key: str, limit: int, window_seconds: int) -> bool:
    """Count one hit for ``key``; return True once it exceeds ``limit`` within the window."""
    cache.add(key, 0, timeout=window_seconds)
    try:
        count = cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    return count > limit
