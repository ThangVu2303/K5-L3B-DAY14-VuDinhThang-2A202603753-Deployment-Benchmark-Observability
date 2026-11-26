"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Biến môi trường (liệt kê đủ trong .env.example):
  PORT, ENVIRONMENT, AGENT_API_KEY, REDIS_URL, RATE_LIMIT_PER_MINUTE,
  DAILY_BUDGET_USD, MONTHLY_BUDGET_USD (tuỳ chọn), LOG_LEVEL, APP_VERSION

Không có secret nào trong code: AGENT_API_KEY không có giá trị mặc định.
Thiếu key thì mọi request /ask bị 401; riêng ENVIRONMENT=production thì app
dừng ngay lúc khởi động (fail fast) thay vì chạy mà không có bảo vệ.
"""
import os
from dataclasses import dataclass, field


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: _env_str("ENVIRONMENT", "development"))
    app_version: str = field(default_factory=lambda: _env_str("APP_VERSION", "1.0.0"))
    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO").upper())

    # Secret: không có giá trị mặc định
    agent_api_key: str = field(default_factory=lambda: _env_str("AGENT_API_KEY", ""))

    redis_url: str = field(default_factory=lambda: _env_str("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))
    # Tuỳ chọn: để trống thì chỉ áp dụng budget theo ngày
    monthly_budget_usd: float | None = field(default_factory=lambda: _env_float("MONTHLY_BUDGET_USD", None))

    def __post_init__(self):
        if self.rate_limit_per_minute <= 0:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be > 0")
        if self.daily_budget_usd < 0:
            raise ValueError("DAILY_BUDGET_USD must be >= 0")
        if self.monthly_budget_usd is not None and self.monthly_budget_usd < 0:
            raise ValueError("MONTHLY_BUDGET_USD must be >= 0")
        if self.environment == "production" and not self.agent_api_key:
            raise ValueError("AGENT_API_KEY must be set when ENVIRONMENT=production")


settings = Settings()
