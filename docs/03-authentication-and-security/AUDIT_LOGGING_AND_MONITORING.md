# Audit Logging & Security Monitoring

This document details the security logging architecture, correlation ID request tracing, sensitive data redaction, and database security audit logging implemented for OWASP A09 (Security Logging and Monitoring Failures).

---

## Architecture Overview

The logging system combines request-scoped context tracking, automatic credential redaction, structured JSON logging for SIEM integrations, and persistent database audit tracking.

```text
[Incoming HTTP Request]
       │
       ▼
┌─────────────────────────────────────────┐
│ CorrelationIdMiddleware                 │
│ 1. Extract / generate X-Request-ID      │
│ 2. Set ContextVars (req_id, ip, ua)     │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Application Execution / Security Events │
│ (AuditLogger / SensitiveDataRedactor)   │
└─────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────┐
       ▼                                         ▼
┌─────────────────────────────────────────┐   ┌─────────────────────────────────────────┐
│ Console / File Log Output               │   │ Database Audit Log                      │
│ (JSONFormatter / TextFormatter)        │   │ (AuditLog ORM Table in PostgreSQL)      │
└─────────────────────────────────────────┘   └─────────────────────────────────────────┘
```

---

## 1. Request Correlation ID Tracing (`CorrelationIdMiddleware`)

Every HTTP request is assigned a unique Correlation ID (`X-Request-ID` header) to trace logs across distributed services.

### Middleware Implementation (`app/core/middleware/correlation.py`)

1. **Extraction / Generation**: Checks incoming headers for `X-Request-ID`. If missing or empty, generates a UUIDv4 string (`str(uuid.uuid4())`).
2. **Reverse Proxy Support**: Extracts true client IP from `X-Forwarded-For` header when running behind reverse proxies (Nginx, Traefik, AWS ALB).
3. **Context Variable Binding**: Binds metadata to Python `contextvars`:
    - `request_id_ctx`: `X-Request-ID` UUID string.
    - `client_ip_ctx`: Client IP address.
    - `user_agent_ctx`: Request `User-Agent` header.
4. **Header Injection**: Attaches `X-Request-ID` to the outgoing HTTP response headers for client-side tracing.

---

## 2. Structured JSON Logger & Redaction (`app/core/logging.py`)

Log formatting and sensitive data redactor filters are initialized globally via `setup_logging()`.

### JSON Formatter Schema (`JSONFormatter`)

In production mode (`DEBUG=False` and `LOG_FORMAT="json"`), logs are formatted as single-line JSON objects suitable for SIEM aggregators (Datadog, Elasticsearch, CloudWatch):

```json
{
    "timestamp": "2026-08-09T11:40:00.123456+00:00",
    "level": "INFO",
    "logger": "app.auth.service",
    "message": "[AUDIT] AUTH_LOGIN_SUCCESS | status=SUCCESS user_id=123e4567-e89b-12d3-a456-426614174000 ip=127.0.0.1 req_id=9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "request_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "client_ip": "127.0.0.1",
    "user_agent": "Mozilla/5.0 ...",
    "extra": {
        "audit_data": {
            "audit_event": "AUTH_LOGIN_SUCCESS",
            "audit_status": "SUCCESS"
        }
    }
}
```

### Sensitive Data Redaction (`SensitiveDataRedactor`)

To prevent sensitive credentials, tokens, or headers from leaking into log files or monitoring dashboards, a custom `logging.Filter` (`SensitiveDataRedactor`) automatically redacts targeted keys:

- **Redacted Keys**: `password`, `confirm_password`, `new_password`, `current_password`, `token`, `access_token`, `refresh_token`, `otp`, `otp_code`, `code`, `secret_key`, `authorization`, `cookie`, `bearer`, `api_key`.
- **Bearer Header Redaction**: Regex pattern matching sanitizes `Bearer eyJhbGci...` to `Bearer ***REDACTED***`.
- **Recursive Sanitization**: Recursively parses log strings, tuples, and dictionaries, replacing sensitive values with `"***REDACTED***"`.

---

## 3. Security Audit Logging (`app/core/audit.py`)

Critical security events are categorized by `AuditEventType` and `AuditStatus` and logged via `AuditLogger.log_event(...)`.

### Audit Event Categories (`AuditEventType`)

- **Authentication**: `AUTH_REGISTER_ATTEMPT`, `AUTH_REGISTER_SUCCESS`, `AUTH_LOGIN_SUCCESS`, `AUTH_LOGIN_FAILED`, `AUTH_LOCKOUT_TRIGGERED`, `AUTH_LOGOUT`, `AUTH_REFRESH_SUCCESS`, `AUTH_REFRESH_REVOKED_REUSE` (Token theft alert).
- **Access Control**: `ACCESS_DENIED_UNAUTHENTICATED`, `ACCESS_DENIED_UNAUTHORIZED`, `ACCOUNT_STATUS_DENIED`.
- **Threat Detection**: `RATE_LIMIT_EXCEEDED`, `HONEYPOT_TRIGGERED`, `INTEGRITY_CHECK_FAILED`.
- **Administration**: `ADMIN_USER_LISTED`, `ADMIN_USER_VIEWED`, `ADMIN_USER_STATUS_CHANGED`, `ADMIN_SYSTEM_INFO_ACCESSED`.

### Severity Auto-Assignment

`AuditLogger` dynamically maps security event outcomes to Python logging levels:

| Event Status / Category | Log Severity | Trigger Condition                                                                                                                                                            |
| :---------------------- | :----------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ALERT`                 | `CRITICAL`   | Security alerts like token theft reuse (`AUTH_REFRESH_REVOKED_REUSE`) or HMAC tampering (`INTEGRITY_CHECK_FAILED`).                                                          |
| `FAILURE` / `BLOCKED`   | `WARNING`    | Account lockouts (`AUTH_LOCKOUT_TRIGGERED`), honeypot traps (`HONEYPOT_TRIGGERED`), rate limits (`RATE_LIMIT_EXCEEDED`), unauthorized access (`ACCESS_DENIED_UNAUTHORIZED`). |
| `SUCCESS`               | `INFO`       | Successful logins, registrations, profile updates, and admin actions.                                                                                                        |

### PostgreSQL Persistence (`audit_logs` Table)

When a database session (`db`) is passed to `AuditLogger.log_event(...)`, the event is saved to the `audit_logs` table in PostgreSQL:

```python
audit_logger.log_event(
    event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
    status=AuditStatus.SUCCESS,
    user_id=user.id,
    db=db,
)
```

The database log record persists `event_type`, `status`, `user_id` (with `SET NULL` on user deletion to preserve history), `client_ip`, `user_agent`, `request_id`, `details` (JSON), and `created_at`.
