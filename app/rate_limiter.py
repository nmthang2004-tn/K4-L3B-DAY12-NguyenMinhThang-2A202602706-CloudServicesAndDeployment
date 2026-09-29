
"""CP3 — Sliding-window rate limiting bằng Redis."""

from __future__ import annotations

import time
import uuid

from fastapi import HTTPException, status

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, client, limit_per_minute: int) -> None:
        self.client = client
        self.limit = limit_per_minute

    @staticmethod
    def _key(user_id: str) -> str:
        """Mỗi user có một Redis key riêng."""
        return f"ratelimit:{user_id}"

    def hit_count(
        self,
        user_id: str,
        now: float | None = None,
    ) -> int:
        """Đếm số request trong 60 giây gần nhất."""

        # 1. Lấy thời điểm hiện tại
        now = now if now is not None else time.time()

        # 2. Lấy Redis key
        key = self._key(user_id)

        # 3. Xóa request cũ ngoài cửa sổ
        self.client.zremrangebyscore(
            key,
            0,
            now - WINDOW_SECONDS,
        )

        # 4. Đếm request còn lại
        return self.client.zcard(key)

    def check(
        self,
        user_id: str,
        now: float | None = None,
    ) -> None:
        """Kiểm tra quota và ghi nhận request hợp lệ."""

        # 1. Xác định thời gian hiện tại
        now = now if now is not None else time.time()

        # 2. Đếm trước khi ghi nhận
        count = self.hit_count(user_id, now)

        # 3. Đã đạt giới hạn: trả HTTP 429
        if count >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
                headers={
                    "Retry-After": str(WINDOW_SECONDS)
                },
            )

        # 4. Ghi nhận request mới
        key = self._key(user_id)

        # Timestamp + UUID bảo đảm member duy nhất
        member = f"{now}:{uuid.uuid4().hex}"

        self.client.zadd(
            key,
            {member: now},
        )

        # 5. Đặt TTL tự động dọn key
        self.client.expire(key, WINDOW_SECONDS)
