
"""CP3 — Xác thực bằng API key."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings

ANONYMOUS_USER = "anonymous"


def verify_api_key(
    x_api_key: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    """Kiểm tra X-API-Key và trả về user_id."""

    # 1. Lấy API key từ Settings
    expected_key = get_settings().agent_api_key

    # 2. Kiểm tra key thiếu hoặc không hợp lệ
    if x_api_key is None or not secrets.compare_digest(
        x_api_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )

    # 3. Hợp lệ: trả về user_id hoặc anonymous
    return x_user_id if x_user_id else ANONYMOUS_USER
