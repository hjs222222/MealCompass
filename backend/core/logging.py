"""JSON structured logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
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

#: 日志文件路径与轮转上限（避免本地开发时日志无限膨胀）。
#: 启动脚本（scripts/start_mealcompass.ps1）还会把 stderr 重定向到 .tmp/launch/；
#: 这里再加一个自轮转的文件 handler，让应用日志本身有大小上限。
LOG_DIR = Path(__file__).resolve().parents[2] / ".tmp" / "logs"
LOG_FILE = LOG_DIR / "mealcompass.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3  # 保留 3 个滚动文件，最多 ~20 MB


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
    # 清理旧 handler（重复调用时不要叠加）
    for old in list(root.handlers):
        if getattr(old, "name", "") in {"mealcompass-json", "mealcompass-file"}:
            root.removeHandler(old)
            old.close()

    formatter = JsonFormatter()

    # stderr handler（保留，被启动脚本重定向到 .tmp/launch/backend.err.log）
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.name = "mealcompass-json"
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # 文件 handler：自轮转，避免日志无限膨胀
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.name = "mealcompass-file"
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        # 日志文件写不进去不能让应用起不来；stderr 仍然可用
        stream_handler.handle(
            logging.LogRecord(
                name="mealcompass.logging",
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg="file log handler unavailable: %s",
                args=(exc,),
                exc_info=None,
            )
        )
