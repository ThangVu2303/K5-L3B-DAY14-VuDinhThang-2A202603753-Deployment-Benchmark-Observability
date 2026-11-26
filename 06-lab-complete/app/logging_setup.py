"""
Structured logging (tiêu chí 10): mỗi dòng log là đúng 1 JSON object.

  logger.info("request", extra={"fields": {"path": "/ask", "status": 200}})
  → {"ts": "...", "lvl": "INFO", "logger": "agent", "event": "request", "path": "/ask", "status": 200}

Dùng ensure_ascii=True để log chỉ có ký tự ASCII: không bao giờ lỗi encode khi stdout
không phải UTF-8 (lỗi UnicodeEncodeError gặp ở Part 1 trên Windows).
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Log của uvicorn cũng ra JSON; access log tắt vì app tự log mỗi request
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
    logging.getLogger("uvicorn.access").disabled = True

    return logging.getLogger("agent")
