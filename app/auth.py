"""API key authentication dependency."""
from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY = os.environ.get("API_KEY", "")


def require_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Validate X-API-Key header. Skip if API_KEY env var is not set."""
    if not _API_KEY:
        # No API key configured — auth disabled (dev mode)
        return "dev"
    if not api_key or api_key != _API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Set X-API-Key header.",
        )
    return api_key
