"""
Audit Log Service — Business logic for persisting and querying database Audit Logs.
"""

import logging
import uuid
from typing import Any, Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core import timezone as tz
from app.modules.audit_log.models import AuditLog
from app.modules.audit_log.schemas import AuditLogResponse, AuditLogListResponse

logger = logging.getLogger("app.audit_log.service")


class AuditLogService:
    """Service class for database audit log operations."""

    @staticmethod
    def create_audit_log(
        db: Session,
        event_type: str,
        status: str,
        user_id: Optional[uuid.UUID | str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> Optional[AuditLog]:
        """
        Persist a new AuditLog row into the database.

        Args:
            db: SQLAlchemy Database session.
            event_type: Event type identifier string (e.g. AUTH_LOGIN_SUCCESS).
            status: Status string (SUCCESS, FAILURE, BLOCKED, ALERT).
            user_id: Optional UUID or string user ID.
            client_ip: Optional IP address.
            user_agent: Optional User-Agent string.
            request_id: Optional correlation request ID.
            details: Optional dictionary of extra event details.

        Returns:
            The created AuditLog ORM instance or None if database write fails.
        """
        try:
            parsed_user_id: Optional[uuid.UUID] = None
            if user_id:
                if isinstance(user_id, uuid.UUID):
                    parsed_user_id = user_id
                else:
                    try:
                        parsed_user_id = uuid.UUID(str(user_id))
                    except ValueError:
                        parsed_user_id = None

            audit_log = AuditLog(
                event_type=event_type,
                status=status,
                user_id=parsed_user_id,
                client_ip=client_ip,
                user_agent=user_agent[:512] if user_agent else None,
                request_id=request_id,
                details=details,
                created_at=tz.now(),
            )
            db.add(audit_log)
            db.commit()
            db.refresh(audit_log)
            return audit_log
        except Exception as err:
            db.rollback()
            logger.error(
                "Failed to write audit log to database | event=%s status=%s error=%s",
                event_type, status, err, exc_info=True,
            )
            return None

    @staticmethod
    def list_audit_logs(
        db: Session,
        target_user_id: Optional[uuid.UUID] = None,
        event_type: Optional[str] = None,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AuditLogListResponse:
        """
        Return a paginated list of audit logs with optional filters.

        Args:
            db: Database session.
            target_user_id: Optional target user UUID filter.
            event_type: Optional event_type filter.
            status_filter: Optional status filter.
            skip: Number of records to skip.
            limit: Maximum records per page (capped at 100).

        Returns:
            AuditLogListResponse paginated list.
        """
        limit = min(limit, 100)

        query = db.query(AuditLog)

        if target_user_id:
            query = query.filter(AuditLog.user_id == target_user_id)
        if event_type:
            query = query.filter(AuditLog.event_type == event_type)
        if status_filter:
            query = query.filter(AuditLog.status == status_filter)

        total = query.count()
        logs = query.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit).all()

        items = []
        for log in logs:
            items.append(
                AuditLogResponse(
                    id=str(log.id),
                    event_type=log.event_type,
                    status=log.status,
                    user_id=str(log.user_id) if log.user_id else None,
                    user_email=log.user.email if log.user else None,
                    user_username=log.user.username if log.user else None,
                    client_ip=log.client_ip,
                    user_agent=log.user_agent,
                    request_id=log.request_id,
                    details=log.details,
                    created_at=log.created_at,
                )
            )

        return AuditLogListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
        )
