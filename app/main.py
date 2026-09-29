
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


SERVICE_NAME = "day12-agent"
SERVICE_VERSION = "1.0.0"


# ============================================================
# Providers — Dependency Injection
# ============================================================

@lru_cache(maxsize=1)
def get_store() -> ConversationStore:
    return ConversationStore(get_redis_client())


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter(
        get_redis_client(),
        get_settings().rate_limit_per_minute,
    )


@lru_cache(maxsize=1)
def get_cost_guard() -> CostGuard:
    return CostGuard(
        get_redis_client(),
        get_settings().monthly_budget_usd,
    )


# ============================================================
# Application Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Chạy khi ứng dụng khởi động và tắt."""

    lifecycle.install()

    log_event(
        "service_started",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
    )

    yield

    log_event(
        "service_stopped",
        service=SERVICE_NAME,
    )


app = FastAPI(
    title="Day 12 Production Agent",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


# ============================================================
# Request Schema
# ============================================================

class AskRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
    )


# ============================================================
# Health — CP1
# ============================================================

@app.get("/health")
def health():
    """Liveness probe — kiểm tra process còn sống hay không."""

    if lifecycle.shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
            },
        )

    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


# ============================================================
# Readiness — CP4
# ============================================================

@app.get("/ready")
def ready(
    store: ConversationStore = Depends(get_store),
):
    """Readiness probe — kiểm tra khả năng phục vụ request."""

    # 1. Kiểm tra trạng thái shutdown
    if lifecycle.shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
            },
        )

    # 2. Kiểm tra kết nối Redis
    if not store.ping():
        return JSONResponse(
            status_code=503,
            content={
                "status": "not ready",
                "redis": False,
            },
        )

    # 3. Redis hoạt động bình thường
    return {
        "status": "ready",
        "redis": True,
    }


# ============================================================
# Main Endpoint — CP3
# ============================================================

@app.post("/ask")
def ask(
    payload: AskRequest,
    user_id: str = Depends(verify_api_key),
    store: ConversationStore = Depends(get_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
    guard: CostGuard = Depends(get_cost_guard),
):
    """Xử lý request theo đúng thứ tự CP3."""

    # --------------------------------------------------------
    # STEP 1 — RATE LIMIT
    # HTTP 429 nếu user gửi quá nhiều request
    # --------------------------------------------------------

    limiter.check(user_id)

    # --------------------------------------------------------
    # STEP 2 — COST GUARD
    # HTTP 402 nếu user đã hết ngân sách
    # --------------------------------------------------------

    guard.check(user_id)

    # --------------------------------------------------------
    # STEP 3 — GET CONVERSATION HISTORY
    # --------------------------------------------------------

    history = store.get_history(user_id)

    # --------------------------------------------------------
    # STEP 4 — CALL LLM
    # --------------------------------------------------------

    result = ask_llm(
        payload.question,
        history,
    )

    # --------------------------------------------------------
    # STEP 5 — SAVE CONVERSATION
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
# Local Development
# ============================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
    )
