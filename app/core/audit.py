"""
Security Audit Logging & Monitoring Module.

Security Logging and Monitoring Failures
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Provides standardized security audit logging for all critical security events:
  - Authentication (Register, Login, Logout, Refresh, Password Reset, MFA/OTP)
  - Access Control & Authorization (401 Unauthenticated, 403 Forbidden, Status block)
  - Threat Detection (Honeypot trigger, Rate limit exceeded, Revoked token theft)
  - Data & System Integrity (HMAC Tamper detection, Password changes)
  - Administrative Actions (User listing, user status mutation, system info access)

Ensures every security event is recorded with complete contextual metadata
(timestamp, event_type, status, user_id, client_ip, user_agent, request_id, details)
and proper log severity level (INFO, WARNING, ERROR, CRITICAL).
"""

import logging
from enum import Enum
from typing import Any, Optional

from app.core import timezone as tz
from app.core.logging import (
    client_ip_ctx,
    redact_sensitive_data,
    request_id_ctx,
    user_agent_ctx,
)

from sqlalchemy.orm import Session

logger = logging.getLogger("app.audit")


class AuditEventType(str, Enum):
    # Authentication & Registration Events
    AUTH_REGISTER_ATTEMPT = "AUTH_REGISTER_ATTEMPT"
    AUTH_REGISTER_SUCCESS = "AUTH_REGISTER_SUCCESS"
    AUTH_REGISTER_FAILED = "AUTH_REGISTER_FAILED"
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    AUTH_LOCKOUT_TRIGGERED = "AUTH_LOCKOUT_TRIGGERED"
    AUTH_BLOCKED_LOCKED = "AUTH_BLOCKED_LOCKED"
    AUTH_BLOCKED_STATUS = "AUTH_BLOCKED_STATUS"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    AUTH_SESSION_REVOKED = "AUTH_SESSION_REVOKED"
    AUTH_SESSIONS_REVOKED_ALL = "AUTH_SESSIONS_REVOKED_ALL"

    # Password & Account Recovery Events
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_VERIFIED = "PASSWORD_RESET_VERIFIED"
    PASSWORD_RESET_SUCCESS = "PASSWORD_RESET_SUCCESS"
    PASSWORD_CHANGE_SUCCESS = "PASSWORD_CHANGE_SUCCESS"
    PASSWORD_CHANGE_FAILED = "PASSWORD_CHANGE_FAILED"

    # Authorization & Access Control Events
    ACCESS_DENIED_UNAUTHENTICATED = "ACCESS_DENIED_UNAUTHENTICATED"
    ACCESS_DENIED_UNAUTHORIZED = "ACCESS_DENIED_UNAUTHORIZED"
    ACCOUNT_STATUS_DENIED = "ACCOUNT_STATUS_DENIED"

    # Threat & Security Guard Events
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    HONEYPOT_TRIGGERED = "HONEYPOT_TRIGGERED"
    INTEGRITY_CHECK_FAILED = "INTEGRITY_CHECK_FAILED"

    # Admin & Management Audit Events
    ADMIN_USER_LISTED = "ADMIN_USER_LISTED"
    ADMIN_USER_VIEWED = "ADMIN_USER_VIEWED"
    ADMIN_USER_STATUS_CHANGED = "ADMIN_USER_STATUS_CHANGED"
    ADMIN_SYSTEM_INFO_ACCESSED = "ADMIN_SYSTEM_INFO_ACCESSED"

    # Project Workspace & Lifecycle Audit Events
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    PROJECT_STATUS_CHANGED = "PROJECT_STATUS_CHANGED"
    PROJECT_ORDER_CHANGED = "PROJECT_ORDER_CHANGED"
    PROJECT_DELETED = "PROJECT_DELETED"

    # Collaborator & RBAC Audit Events
    COLLABORATOR_INVITED = "COLLABORATOR_INVITED"
    COLLABORATOR_INVITATION_REVOKED = "COLLABORATOR_INVITATION_REVOKED"
    COLLABORATOR_INVITATION_ACCEPTED = "COLLABORATOR_INVITATION_ACCEPTED"
    COLLABORATOR_INVITATION_DECLINED = "COLLABORATOR_INVITATION_DECLINED"
    COLLABORATOR_ROLE_UPDATED = "COLLABORATOR_ROLE_UPDATED"
    COLLABORATOR_REMOVED = "COLLABORATOR_REMOVED"


class AuditStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"
    ALERT = "ALERT"


class AuditLogger:
    """
    Centralized Security Audit Logger.

    Ensures consistent structure, log level assignment, sensitive data redaction,
    and database persistence across all security audit events.
    """

    @staticmethod
    def log_event(
        event_type: AuditEventType | str,
        status: AuditStatus | str,
        user_id: Optional[Any] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        level: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        """
        Record a structured security audit event and persist it to PostgreSQL database when db is provided.

        Args:
            event_type: AuditEventType enum value or event string identifier.
            status: AuditStatus enum value ('SUCCESS', 'FAILURE', 'BLOCKED', 'ALERT').
            user_id: Optional UUID/string ID of affected or acting user.
            client_ip: Optional client IP address (defaults to context var if omitted).
            user_agent: Optional User-Agent header (defaults to context var if omitted).
            details: Additional non-sensitive event metadata dictionary.
            level: Optional explicit logging level (e.g. logging.WARNING).
            db: Optional SQLAlchemy Database session to persist audit event to database.

        Returns:
            The formatted audit event dictionary.
        """
        event_name = event_type.value if isinstance(event_type, AuditEventType) else str(event_type)
        status_name = status.value if isinstance(status, AuditStatus) else str(status)

        ip = client_ip or client_ip_ctx.get()
        ua = user_agent or user_agent_ctx.get()
        req_id = request_id_ctx.get()

        clean_details = redact_sensitive_data(details or {})

        audit_payload = {
            "audit_event": event_name,
            "audit_status": status_name,
            "timestamp": tz.now().isoformat(),
            "request_id": req_id,
            "user_id": str(user_id) if user_id is not None else None,
            "client_ip": ip,
            "user_agent": ua,
            "details": clean_details,
        }

        # 1. Database Persistence if DB Session provided
        if db is not None:
            try:
                from app.modules.audit_log.service import AuditLogService
                AuditLogService.create_audit_log(
                    db=db,
                    event_type=event_name,
                    status=status_name,
                    user_id=user_id,
                    client_ip=ip,
                    user_agent=ua,
                    request_id=req_id if req_id != "-" else None,
                    details=clean_details,
                )
            except Exception as db_err:
                logger.error("Failed persisting audit log to database | error=%s", db_err, exc_info=True)

        # 2. Determine appropriate log level if not explicitly provided
        if level is None:
            if status_name == AuditStatus.ALERT.value or event_name in (
                AuditEventType.INTEGRITY_CHECK_FAILED.value,
            ):
                level = logging.CRITICAL
            elif status_name in (AuditStatus.FAILURE.value, AuditStatus.BLOCKED.value) or event_name in (
                AuditEventType.AUTH_LOCKOUT_TRIGGERED.value,
                AuditEventType.HONEYPOT_TRIGGERED.value,
                AuditEventType.RATE_LIMIT_EXCEEDED.value,
                AuditEventType.ACCESS_DENIED_UNAUTHORIZED.value,
            ):
                level = logging.WARNING
            else:
                level = logging.INFO

        msg = (
            f"[AUDIT] {event_name} | status={status_name} "
            f"user_id={audit_payload['user_id'] or 'n/a'} ip={ip} req_id={req_id}"
        )

        logger.log(level, msg, extra={"audit_data": audit_payload})
        return audit_payload


# Singleton instance alias
audit_logger = AuditLogger()

