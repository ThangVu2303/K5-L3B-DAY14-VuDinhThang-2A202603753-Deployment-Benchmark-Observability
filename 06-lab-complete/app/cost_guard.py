"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM (tính theo token) vào Redis, dùng chung cho mọi worker / instance
  • Tổng chi phí trong ngày (UTC) ≥ DAILY_BUDGET_USD → HTTP 402
  • Nếu có MONTHLY_BUDGET_USD: tổng chi phí trong tháng ≥ budget tháng → HTTP 402
  • Key theo ngày / tháng (cost:daily:2026-11-26, cost:monthly:2026-11) nên sang ngày /
    tháng mới tự reset; TTL để Redis tự dọn key cũ
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAILY_TTL_SECONDS = 2 * 24 * 3600
MONTHLY_TTL_SECONDS = 32 * 24 * 3600


def _keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return f"cost:daily:{now:%Y-%m-%d}", f"cost:monthly:{now:%Y-%m}"


def estimate_tokens(text: str) -> int:
    """Ước lượng thô ~4 ký tự / token (mock LLM không trả usage thật)."""
    return max(1, len(text) // 4)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_key, monthly_key = _keys()
    daily_raw, monthly_raw = r.mget(daily_key, monthly_key)
    daily = float(daily_raw or 0)
    monthly = float(monthly_raw or 0)

    if daily >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "spent_usd": round(daily, 6),
                "budget_usd": settings.daily_budget_usd,
                "resets_at": "00:00 UTC",
            },
        )
    if settings.monthly_budget_usd is not None and monthly >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "spent_usd": round(monthly, 6),
                "budget_usd": settings.monthly_budget_usd,
                "resets_at": "first day of next month (UTC)",
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    daily_key, monthly_key = _keys()
    pipe = r.pipeline(transaction=True)
    pipe.incrbyfloat(daily_key, cost)
    pipe.expire(daily_key, DAILY_TTL_SECONDS)
    pipe.incrbyfloat(monthly_key, cost)
    pipe.expire(monthly_key, MONTHLY_TTL_SECONDS)
    pipe.execute()
    return cost
