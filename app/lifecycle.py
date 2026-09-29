
"""CP4 — Graceful shutdown với SIGTERM và SIGINT."""

from __future__ import annotations

import signal


class Lifecycle:
    """Quản lý trạng thái vòng đời của process."""

    def __init__(self) -> None:

        # Trạng thái ban đầu: service đang hoạt động
        self.shutting_down = False

        # Lưu các signal handler trước đó
        self._previous: dict = {}

    def request_shutdown(
        self,
        signum=None,
        frame=None,
    ) -> None:
        """Nhận tín hiệu shutdown và gọi lại handler cũ."""

        # 1. Đánh dấu service đang shutdown
        self.shutting_down = True

        # 2. Lấy handler đã được đăng ký trước đó
        previous = self._previous.get(signum)

        # 3. Gọi lại handler cũ nếu callable
        if callable(previous):
            previous(signum, frame)

    def install(self) -> None:
        """Đăng ký SIGTERM, SIGINT và lưu handler cũ."""

        for sig in (
            signal.SIGTERM,
            signal.SIGINT,
        ):

            # 1. Lưu signal handler hiện tại
            self._previous[sig] = signal.getsignal(sig)

            # 2. Đăng ký handler của ứng dụng
            signal.signal(
                sig,
                self.request_shutdown,
            )


# Một instance dùng chung trong ứng dụng
lifecycle = Lifecycle()
