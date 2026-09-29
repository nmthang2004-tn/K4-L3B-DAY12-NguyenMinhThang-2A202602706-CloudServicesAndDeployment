
"""Agent service — điểm ráp nối của cả lab (CP1, CP3, CP4).

Luồng một request tới /ask:

    client
      |
      v
    verify_api_key
      |
      v
    rate_limiter
      |
      v
    cost_guard
      |
      v
    store.get_history
      |
      v
    ask_llm
      |
      v
    store.append x 2
      |
      v
    cost_guard.record
      |
      v
    log_event
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.mock_llm import ask_llm

from .auth import verify_api_key
from .config import get_settings
from .cost_guard import CostGuard
from .lifecycle import lifecycle
from .logging_utils import log_event
from .rate_limiter import RateLimiter
from .store import ConversationStore, get_redis_client


# ============================================================
# SERVICE INFORMATION
# ============================================================

SERVICE_NAME = "day12-agent"
SERVICE_VERSION = "1.0.0"


# ============================================================
# PROVIDERS — DEPENDENCY INJECTION
# ============================================================

@lru_cache(maxsize=1)
def get_store() -> ConversationStore:
    """Khởi tạo ConversationStore sử dụng Redis."""
    return ConversationStore(get_redis_client())


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Khởi tạo RateLimiter từ Settings."""
    return RateLimiter(
        get_redis_client(),
        get_settings().rate_limit_per_minute,
    )


@lru_cache(maxsize=1)
def get_cost_guard() -> CostGuard:
    """Khởi tạo CostGuard từ Settings."""
    return CostGuard(
        get_redis_client(),
        get_settings().monthly_budget_usd,
    )


# ============================================================
# APPLICATION LIFESPAN — CP4
# ============================================================

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Quản lý vòng đời của ứng dụng."""

    # Đặt lại trạng thái khi khởi động
    lifecycle.shutting_down = False

    # Đăng ký signal handler SIGTERM và SIGINT
    lifecycle.install()

    # Ghi log khi service khởi động
    log_event(
        "service_started",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
    )

    try:
        yield

    finally:
        # Ghi log khi service dừng
        log_event(
            "service_stopped",
            service=SERVICE_NAME,
        )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Day 12 Production Agent",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


# ============================================================
# REQUEST SCHEMA
# ============================================================

class AskRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
    )


# ============================================================
# CP1 — LIVENESS ENDPOINT
# ============================================================

@app.get("/health")
def health():
    """Kiểm tra process còn sống hay đang shutdown.

    Không gọi Redis hoặc bất kỳ dependency bên ngoài nào.
    """

    # Service đang shutdown
    if lifecycle.shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
            },
        )

    # Service hoạt động bình thường
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


# ============================================================
# CP4 — READINESS ENDPOINT
# ============================================================

@app.get("/ready")
def ready(
    store: ConversationStore = Depends(get_store),
):
    """Kiểm tra service có sẵn sàng nhận request không."""

    # STEP 1: Kiểm tra trạng thái shutdown
    if lifecycle.shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
            },
        )

    # STEP 2: Kiểm tra Redis
    if not store.ping():
        return JSONResponse(
            status_code=503,
            content={
                "status": "not ready",
                "redis": False,
            },
        )

    # STEP 3: Redis hoạt động bình thường
    return {
        "status": "ready",
        "redis": True,
    }


# ============================================================
# CP3 — MAIN ENDPOINT /ask
# ============================================================

@app.post("/ask")
def ask(
    payload: AskRequest,
    user_id: str = Depends(verify_api_key),
    store: ConversationStore = Depends(get_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
    guard: CostGuard = Depends(get_cost_guard),
):
    """Xử lý request theo đúng thứ tự CP3.

    Authentication
    -> Rate limiting
    -> Cost guard
    -> Get history
    -> Call LLM
    -> Save history
    -> Record cost
    -> Structured logging
    -> Response
    """

    # --------------------------------------------------------
    # STEP 1 — RATE LIMITING
    # Trả HTTP 429 nếu vượt giới hạn request
    # --------------------------------------------------------

    limiter.check(user_id)

    # --------------------------------------------------------
    # STEP 2 — COST GUARD
    # Trả HTTP 402 nếu đã hết ngân sách tháng
    # --------------------------------------------------------

    guard.check(user_id)

    # --------------------------------------------------------
    # STEP 3 — GET CONVERSATION HISTORY
    # Đọc lịch sử hội thoại từ Redis
    # --------------------------------------------------------

    history = store.get_history(user_id)

    # --------------------------------------------------------
    # STEP 4 — CALL LLM
    # Chỉ gọi LLM sau khi vượt qua các lớp bảo vệ
    # --------------------------------------------------------

    result = ask_llm(
        payload.question,
        history,
    )

    # --------------------------------------------------------
    # STEP 5 — SAVE CONVERSATION
    # Lưu cả câu hỏi và câu trả lời vào Redis
    # --------------------------------------------------------

    store.append(
        user_id,
        "user",
        payload.question,
    )

    store.append(
        user_id,
        "assistant",
        result["answer"],
    )

    # --------------------------------------------------------
    # STEP 6 — RECORD ACTUAL COST
    # Cộng dồn chi phí LLM vừa phát sinh
    # --------------------------------------------------------

    guard.record(
        user_id,
        result["cost_usd"],
    )

    # --------------------------------------------------------
    # STEP 7 — STRUCTURED LOGGING
    # --------------------------------------------------------

    log_event(
        "ask_completed",
        user_id=user_id,
        tokens_in=result["tokens_in"],
        tokens_out=result["tokens_out"],
        cost_usd=result["cost_usd"],
    )

    # --------------------------------------------------------
    # STEP 8 — RETURN RESPONSE
    # --------------------------------------------------------

    return {
        "answer": result["answer"],
        "user_id": user_id,
        "history_length": len(history),
        "cost_usd": result["cost_usd"],
        "tokens": {
            "in": result["tokens_in"],
            "out": result["tokens_out"],
        },
    }


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
    )
