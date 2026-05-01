import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import get_settings


def _constant_time_in(token: str, allowed: list[str]) -> bool:
    # Constant-time comparison to mitigate timing attacks.
    ok = False
    for candidate in allowed:
        if hmac.compare_digest(token, candidate):
            ok = True
    return ok


async def require_api_key(authorization: Optional[str] = Header(default=None)) -> str:
    settings = get_settings()
    if not settings.auth_required:
        return "anonymous:web"
    if not settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API keys not configured",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if not _constant_time_in(token, settings.api_keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Return a stable identifier for audit (hash-prefix, never the raw token).
    return f"key:{token[:6]}"
