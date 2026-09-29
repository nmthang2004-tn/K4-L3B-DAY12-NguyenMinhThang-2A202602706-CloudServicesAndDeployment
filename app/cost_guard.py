
"""CP3 — Cost guard: giới hạn chi phí theo tháng."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status

# Lưu dữ liệu thêm khoảng 40 ngày để đối soát
KEY_TTL_SECONDS = 40 * 24 * 3600


class CostGuard:
    def __init__(
        self,
        client,
        monthly_budget_usd: float,
    ) -> None:
        self.client = client
        self.budget = monthly_budget_usd

    @staticmethod
    def current_month() -> str:
        """Tháng hiện tại theo UTC, định dạng YYYY-MM."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    @classmethod
    def _key(
        cls,
        user_id: str,
        month: str | None = None,
    ) -> str:
        """Tạo key theo user và tháng."""
        return f"cost:{user_id}:{month or cls.current_month()}"

    def spent(
        self,
        user_id: str,
        month: str | None = None,
    ) -> float:
        """Trả về số tiền user đã sử dụng trong tháng."""

        key = self._key(user_id, month)

        # Redis trả None nếu key chưa tồn tại
        value = self.client.get(key)

        if value is None:
            return 0.0

        return float(value)

    def check(
        self,
        user_id: str,
        estimated_cost: float = 0.0,
        month: str | None = None,
    ) -> None:
        """Kiểm tra ngân sách trước khi gọi LLM."""

        # 1. Lấy chi phí đã sử dụng
        current_spent = self.spent(user_id, month)

        # 2. Cộng thêm chi phí dự kiến
        projected_total = current_spent + estimated_cost

        # 3. Chặn nếu vượt ngân sách
        if projected_total > self.budget:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="monthly budget exceeded",
            )

    def record(
        self,
        user_id: str,
        cost: float,
        month: str | None = None,
    ) -> float:
        """Cộng dồn chi phí phát sinh và trả về tổng mới."""

        # 1. Xác định key
        key = self._key(user_id, month)

        # 2. Cộng dồn bằng Redis INCRBYFLOAT
        total = self.client.incrbyfloat(key, cost)

        # 3. Đặt TTL
        self.client.expire(key, KEY_TTL_SECONDS)

        # 4. Trả về tổng chi phí mới
        return float(total)
