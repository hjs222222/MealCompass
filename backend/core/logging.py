"""JSON structured logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from core.exceptions import request_id_context

SENSITIVE_KEYS = frozenset({"password", "token", "secret", "api_key", "authorization", "cookie"})
EXTRA_FIELDS = (
    "method",
    "path",
    "status_code",
    "duration_ms",
    "exception_type",
    "error_code",
    "provider",
    "degraded",
    "operation",
    "traceback",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_context.get(),
        }
        for key in EXTRA_FIELDS:
            if hasattr(record, key) and key not in SENSITIVE_KEYS:
                value = getattr(record, key)
                try:
                    json.dumps(value)
                except (TypeError, ValueError):
                    value = repr(value)
                payload[key] = value
        # Preserve non-sensitive structured extras without leaking LogRecord internals.
        for key, value in record.__dict__.items():
            if (
                key.startswith("_")
                or key in payload
                or key in SENSITIVE_KEYS
                or key
                in {
                    "args",
                    "msg",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "stacklevel",
                    "name",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                }
            ):
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = next((item for item in root.handlers if getattr(item, "name", "") == "mealcompass-json"), None)
    if handler is not None:
        root.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(sys.stderr)
    handler.name = "mealcompass-json"
    root.addHandler(handler)
    handler.setFormatter(JsonFormatter())
