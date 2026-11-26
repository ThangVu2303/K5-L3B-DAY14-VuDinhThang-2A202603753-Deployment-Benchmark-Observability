"""
Rate limiting (tiêu chí 7).

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window log)
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State lưu trong Redis (sorted set, score = timestamp) nên mọi worker / instance
    dùng chung và vẫn còn sau khi restart agent
  • ZREMRANGEBYSCORE → ZCARD → ZADD → PEXPIRE chạy trong MỘT Lua script: Redis chạy
    script nguyên khối, nên 2 worker gọi cùng lúc cũng không lọt quá giới hạn
  • Key Redis dùng hash của API key, không lưu API key thật
"""
import hashlib
import math
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60

# KEYS[1] = key; ARGV = now, window, limit, member
# Trả về {1, remaining} nếu cho qua, {0, oldest_timestamp} nếu bị chặn.
_SLIDING_WINDOW = r.register_script(
    """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        return {0, oldest[2]}
    end
    redis.call('ZADD', key, now, ARGV[4])
    redis.call('PEXPIRE', key, math.ceil(window * 1000))
    return {1, tostring(limit - count - 1)}
    """
)


def _bucket_key(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"ratelimit:{digest}"


def check_rate_limit(key: str) -> int:
    """Raise 429 khi vượt giới hạn. Trả về số request còn lại trong window."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    allowed, value = _SLIDING_WINDOW(
        keys=[_bucket_key(key)],
        args=[now, WINDOW_SECONDS, limit, f"{now:.6f}-{uuid.uuid4().hex[:8]}"],
    )
    if int(allowed) == 1:
        return int(value)

    retry_after = max(1, math.ceil(float(value) + WINDOW_SECONDS - now))
    raise HTTPException(
        status_code=429,
        detail={
            "error": "Rate limit exceeded",
            "limit": limit,
            "window_seconds": WINDOW_SECONDS,
            "retry_after_seconds": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
        },
    )
