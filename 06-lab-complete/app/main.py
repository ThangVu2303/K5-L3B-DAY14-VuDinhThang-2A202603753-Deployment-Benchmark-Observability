"""
Production AI Agent — Part 6 Final Project

Chạy:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Chấm:  python check_production_ready.py

  GET  /health  liveness  — luôn 200 khi process còn sống (không phụ thuộc Redis)
  GET  /ready   readiness — 200 khi Redis kết nối được, 503 khi không hoặc đang shutdown
  POST /ask     X-API-Key → rate limit (Redis) → cost guard (Redis) → LLM → ghi chi phí
"""
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from redis.exceptions import RedisError

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.logging_setup import setup_logging
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask

logger = setup_logging(settings.log_level)

START_TIME = time.time()
_state = {"ready": False}


def log(event: str, level: str = "info", **fields) -> None:
    getattr(logger, level)(event, extra={"fields": fields})


# ─────────────────────────────────────────────────────────
# Lifespan: startup + graceful shutdown (tiêu chí 11)
#
# Khi nhận SIGTERM, uvicorn đóng socket (ngừng nhận request mới), chờ các request
# đang chạy xử lý xong, rồi mới chạy phần sau `yield` để dọn dẹp và thoát với exit
# code 0. App KHÔNG tự đăng ký signal handler để không đè mất handler của uvicorn.
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(
        "startup",
        version=settings.app_version,
        environment=settings.environment,
        port=settings.port,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        daily_budget_usd=settings.daily_budget_usd,
        monthly_budget_usd=settings.monthly_budget_usd,
        api_key_configured=bool(settings.agent_api_key),
        redis_ok=redis_healthy(),
    )
    if not settings.agent_api_key:
        log("api_key_missing", level="warning", detail="AGENT_API_KEY not set, every /ask returns 401")
    _state["ready"] = True
    yield
    _state["ready"] = False
    log("shutdown", detail="in-flight requests finished, closing Redis connections")
    close_redis()
    log("shutdown_complete", uptime_seconds=round(time.time() - START_TIME, 1))


app = FastAPI(
    title="Production AI Agent",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None,
)


# ─────────────────────────────────────────────────────────
# Middleware: log JSON cho mỗi request + chặn stack trace lộ ra client
# ─────────────────────────────────────────────────────────
@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error", extra={"fields": {"request_id": request_id, "path": request.url.path}})
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    log(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=round((time.perf_counter() - started) * 1000, 1),
        request_id=request_id,
    )
    return response


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


# ─────────────────────────────────────────────────────────
# Health checks (tiêu chí 4, 5)
# ─────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Liveness: chỉ trả lời 'process còn sống', không kiểm tra Redis."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi Redis kết nối được và chưa shutdown."""
    if not _state["ready"]:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "starting or shutting down"})
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"ready": False, "reason": "redis unreachable"})
    return {"ready": True, "redis": "ok"}


# ─────────────────────────────────────────────────────────
# Agent endpoint (tiêu chí 6, 7, 8)
# ─────────────────────────────────────────────────────────
@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    try:
        remaining = check_rate_limit(api_key)   # 429 khi vượt giới hạn
        check_budget()                          # 402 khi hết budget, gọi TRƯỚC LLM
    except RedisError as exc:
        log("redis_unavailable", level="error", error=type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable (storage backend unreachable)",
            headers={"Retry-After": "5"},
        )

    answer = llm_ask(body.question)

    input_tokens = estimate_tokens(body.question)
    output_tokens = estimate_tokens(answer)
    try:
        cost = record_cost(input_tokens, output_tokens)
    except RedisError as exc:
        # Câu trả lời đã có, không bắt client chịu lỗi; chỉ ghi log để theo dõi
        cost = None
        log("cost_record_failed", level="error", error=type(exc).__name__)

    log(
        "ask",
        user_id=body.user_id,
        question_chars=len(body.question),
        answer_chars=len(answer),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        rate_limit_remaining=remaining,
    )
    return {
        "question": body.question,
        "answer": answer,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 8) if cost is not None else None,
            "rate_limit_remaining": remaining,
        },
    }
