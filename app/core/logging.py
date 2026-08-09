"""
Security Logging & Monitoring Failures.

Provides:
- Structured JSON and text formatters with automatic contextual injection
  (timestamp, log level, logger name, request ID, client IP, user agent).
- Sensitive data redaction filter to prevent plain-text exposure of credentials,
  tokens, secrets, and authorization headers in logs.
- Central logging setup function (`setup_logging()`).
"""

import json
import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from app.core.config import settings

# Context Variables for Request-scoped Metadata
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
client_ip_ctx: ContextVar[str] = ContextVar("client_ip", default="unknown")
user_agent_ctx: ContextVar[str] = ContextVar("user_agent", default="unknown")

# Sensitive Data Redaction
SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password",
    "confirm_password",
    "new_password",
    "current_password",
    "token",
    "access_token",
    "refresh_token",
    "otp",
    "otp_code",
    "code",
    "secret_key",
    "authorization",
    "cookie",
    "bearer",
    "api_key",
})

# Regex patterns for matching common sensitive key-value pairs in log strings
# e.g., password='foo', "password": "bar", token=12345
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in SENSITIVE_KEYS) + r")\b\s*[:=]\s*(['\"]?)([^'\",\s&]+)\2",
)
# Bearer / Auth header token pattern
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[a-zA-Z0-9\._\-]+")


def redact_sensitive_data(value: Any) -> Any:
    """
    Recursively redact sensitive fields from dictionaries, lists, or string representations.
    """
    if isinstance(value, dict):
        redacted = {}
        for k, v in value.items():
            if str(k).lower() in SENSITIVE_KEYS:
                redacted[k] = "***REDACTED***"
            else:
                redacted[k] = redact_sensitive_data(v)
        return redacted
    elif isinstance(value, (list, tuple)):
        return [redact_sensitive_data(v) for v in value]
    elif isinstance(value, str):
        # Redact bearer tokens
        val = _BEARER_RE.sub(r"\1***REDACTED***", value)
        # Redact key=val / key:"val"
        val = _KEY_VALUE_RE.sub(r"\1=\2***REDACTED***\2", val)
        return val
    return value


class SensitiveDataRedactor(logging.Filter):
    """
    Logging filter that sanitizes log record messages and extra dictionaries
    to ensure sensitive credentials/tokens are never written in plain text.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_data(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_sensitive_data(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_sensitive_data(a) for a in record.args)

        # Redact attributes in record.__dict__ that may contain dict extras
        for key in list(record.__dict__.keys()):
            if key.lower() in SENSITIVE_KEYS:
                setattr(record, key, "***REDACTED***")
            elif isinstance(getattr(record, key), dict):
                setattr(record, key, redact_sensitive_data(getattr(record, key)))

        return True


# Log Formatters
class JSONFormatter(logging.Formatter):
    """
    Structured JSON log formatter for production SIEM and log aggregator integration.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "client_ip": client_ip_ctx.get(),
            "user_agent": user_agent_ctx.get(),
        }

        # Include exception details if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra audit or custom fields passed to logger
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "taskName",
        }
        extra_fields = {
            k: redact_sensitive_data(v)
            for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """
    Human-readable log formatter for local development / console debugging.
    """

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        req_str = f" [{req_id}]" if req_id and req_id != "-" else ""
        base = f"{self.formatTime(record)} | {record.levelname:<8} | {record.name}{req_str} - {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# Central Logger Setup
def setup_logging() -> None:
    """
    Initialize global logging configuration based on settings.

    - Configures root logger and 'app' module loggers.
    - Attaches console stream handler and rotating file handler (if file path configured).
    - Applies `SensitiveDataRedactor` filter to all handlers.
    - Sets appropriate log levels and formatters (JSON vs Text).
    """
    log_level_num = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    if settings.DEBUG or settings.LOG_FORMAT.lower() == "text":
        formatter: logging.Formatter = TextFormatter()
    else:
        formatter = JSONFormatter()

    redactor_filter = SensitiveDataRedactor()

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level_num)
    root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level_num)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redactor_filter)
    root_logger.addHandler(console_handler)

    # File Handler (if log file directory is specified/writable)
    if settings.LOG_FILE_PATH:
        try:
            log_dir = os.path.dirname(settings.LOG_FILE_PATH)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = RotatingFileHandler(
                settings.LOG_FILE_PATH,
                maxBytes=10 * 1024 * 1024,  # 10 MB per file
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level_num)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(redactor_filter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            logging.warning("Could not initialize file log handler: %s", e)

    # Ensure app loggers propagate to root
    app_logger = logging.getLogger("app")
    app_logger.setLevel(log_level_num)
    app_logger.propagate = True
