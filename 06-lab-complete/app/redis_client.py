"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

  • Đọc REDIS_URL từ config
  • redis.from_url() chỉ tạo connection pool, KHÔNG kết nối lúc import,
    nên app vẫn khởi động được (và /health vẫn 200) khi Redis chưa sẵn sàng
  • Timeout ngắn để /ready trả 503 nhanh thay vì treo khi Redis chết
  • redis_healthy() dùng cho GET /ready
"""
import redis
from redis.exceptions import RedisError

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
    health_check_interval=30,
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except (RedisError, OSError):
        return False


def close_redis() -> None:
    try:
        r.close()
    except (RedisError, OSError):
        pass
