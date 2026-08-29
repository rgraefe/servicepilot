import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

REQUEST_ID = contextvars.ContextVar[str | None]("request_id", default=None)
TRACE_RESOURCE = contextvars.ContextVar[str | None]("trace_resource", default=None)

_STANDARD_RECORD_FIELDS = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
)
_TRACE_PATTERN = re.compile(r"^(?P<trace>[0-9a-fA-F]{32})(?:/[^;]+)?(?:;o=[01])?$")


class CloudJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "message": record.getMessage(),
            "logger": record.name,
        }
        request_id = REQUEST_ID.get()
        if request_id:
            payload["request_id"] = request_id
        trace_resource = TRACE_RESOURCE.get()
        if trace_resource:
            payload["logging.googleapis.com/trace"] = trace_resource

        for key, value in record.__dict__.items():
            if (
                key not in _STANDARD_RECORD_FIELDS
                and not key.startswith("_")
                and key not in {"message", "asctime"}
            ):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("servicepilot")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CloudJsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


def cloud_trace_resource(trace_header: str | None, project_id: str | None) -> str | None:
    if not trace_header or not project_id:
        return None
    match = _TRACE_PATTERN.fullmatch(trace_header.strip())
    if match is None:
        return None
    return f"projects/{project_id}/traces/{match.group('trace').lower()}"
