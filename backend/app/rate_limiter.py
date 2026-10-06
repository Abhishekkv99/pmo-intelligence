"""Rate limiting configuration using slowapi."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.auth_service import AuthService


def _get_rate_limit_key(request: Request) -> str:
    """Return the user ID, or the client IP when there is no valid token.

    Authenticated users get per-user limits (fair even behind NAT).
    Unauthenticated requests fall back to IP-based limiting.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            user_id = AuthService.decode_access_token(token)
            return f"user:{user_id}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=["100/minute"],
    storage_uri="memory://",
)
