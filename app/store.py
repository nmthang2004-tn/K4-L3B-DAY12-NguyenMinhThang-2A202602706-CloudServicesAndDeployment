
"""CP4 — Stateless: lưu lịch sử hội thoại trong Redis."""

from __future__ import annotations

import json

import redis

from .config import get_settings


HISTORY_MAX_MESSAGES = 20
HISTORY_TTL_SECONDS = 7 * 24 * 3600


def get_redis_client(url: str | None = None):
    """Tạo Redis client từ URL cấu hình."""

    url = url or get_settings().redis_url

    if url.startswith("fake://"):
        import fakeredis

        return fakeredis.FakeRedis(
            decode_responses=True
        )

    return redis.from_url(
        url,
        decode_responses=True,
    )


class ConversationStore:
    """Lưu lịch sử hội thoại theo từng user trong Redis List."""

    def __init__(self, client) -> None:
        self.client = client

    @staticmethod
    def _key(user_id: str) -> str:
        """Mỗi user có một Redis key riêng."""
        return f"history:{user_id}"

    def ping(self) -> bool:
        """Kiểm tra kết nối Redis."""

        try:
            return bool(self.client.ping())

        except Exception as exc:
            print(
                f"Redis connection failed: {type(exc).__name__}",
                flush=True,
            )
            return False

    def append(
        self,
        user_id: str,
        role: str,
        content: str,
    ) -> None:
        """Thêm message và chỉ giữ 20 message gần nhất."""

        # 1. Tạo Redis key
        key = self._key(user_id)

        # 2. Chuyển message thành JSON
        message = json.dumps(
            {
                "role": role,
                "content": content,
            },
            ensure_ascii=False,
        )

        # 3. Ghi message vào cuối Redis List
        self.client.rpush(key, message)

        # 4. Chỉ giữ 20 message gần nhất
        self.client.ltrim(
            key,
            -HISTORY_MAX_MESSAGES,
            -1,
        )

        # 5. Gia hạn TTL lên 7 ngày
        self.client.expire(
            key,
            HISTORY_TTL_SECONDS,
        )

    def get_history(
        self,
        user_id: str,
    ) -> list[dict]:
        """Lấy toàn bộ lịch sử theo thứ tự cũ nhất đến mới nhất."""

        key = self._key(user_id)

        # Đọc toàn bộ Redis List
        messages = self.client.lrange(
            key,
            0,
            -1,
        )

        # Chuyển từng JSON string thành dictionary
        return [
            json.loads(message)
            for message in messages
        ]

    def clear(self, user_id: str) -> None:
        """Xóa toàn bộ lịch sử hội thoại của một user."""

        self.client.delete(
            self._key(user_id)
        )
