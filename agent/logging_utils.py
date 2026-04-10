"""
Helpers de logging estruturado para CLI e servicos internos.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extra_fields = getattr(record, "extra_fields", None) or {}
        for key, value in extra_fields.items():
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str, *, json_output: bool = True, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: str, message: str, **fields):
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message, extra={"extra_fields": fields})
