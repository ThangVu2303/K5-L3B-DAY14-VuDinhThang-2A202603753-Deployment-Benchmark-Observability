"""
Exercise 4.4 — Cost guard theo tháng, lưu trong Redis.

- Mỗi user có budget $10/tháng.
- Chi tiêu lưu ở key `budget:<user_id>:<YYYY-MM>` nên sang tháng mới là key mới (tự reset).
- Key có TTL 32 ngày để Redis tự dọn key của tháng cũ.
- Kiểm tra và cộng tiền trong cùng một Lua script, Redis chạy script nguyên khối nên
  nhiều instance gọi cùng lúc cũng không vượt budget (không có race "đọc rồi mới ghi").

Chạy thử (cần một Redis ở REDIS_URL, mặc định redis://localhost:6379/0):
    python budget_redis.py
"""
import os
from datetime import datetime, timezone

import redis

MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10"))
KEY_TTL_SECONDS = 32 * 24 * 3600

r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

# KEYS[1] = key budget, ARGV[1] = chi phí ước tính, ARGV[2] = budget, ARGV[3] = TTL
# Trả về 1 nếu còn budget (và đã cộng chi phí), 0 nếu vượt (không cộng gì).
_CHECK_AND_SPEND = r.register_script(
    """
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    local cost = tonumber(ARGV[1])
    if current + cost > tonumber(ARGV[2]) then
        return 0
    end
    redis.call('INCRBYFLOAT', KEYS[1], cost)
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
    return 1
    """
)


def _budget_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"


def check_budget(user_id: str, estimated_cost: float) -> bool:
    """Return True nếu còn budget (và ghi nhận chi phí), False nếu vượt."""
    if estimated_cost < 0:
        raise ValueError("estimated_cost must be >= 0")
    ok = _CHECK_AND_SPEND(
        keys=[_budget_key(user_id)],
        args=[estimated_cost, MONTHLY_BUDGET_USD, KEY_TTL_SECONDS],
    )
    return ok == 1


def spent_this_month(user_id: str) -> float:
    return float(r.get(_budget_key(user_id)) or 0)


if __name__ == "__main__":
    user = "demo-user"
    r.delete(_budget_key(user))
    for i in range(1, 6):
        ok = check_budget(user, 3.0)
        print(f"request {i}: cost $3.00 -> {'OK ' if ok else 'BLOCKED (402)'}  spent=${spent_this_month(user):.2f}")
    print(f"key={_budget_key(user)} ttl={r.ttl(_budget_key(user))}s")
