"""
Audit Log Admin API Router.

Admin Audit Log Retrieval
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.rbac import require_admin_or_developer
from app.modules.auth.models import User
from app.modules.audit_log.schemas import AuditLogListResponse
from app.modules.audit_log.service import AuditLogService
from app.shared import responses as res

router = APIRouter()


@router.get(
    "",
    summary="List database security audit logs",
    description="Retrieve paginated security audit logs with filtering by user, event type, and status. Restricted to ADMIN users.",
    response_description="Paginated list of security audit log records.",
)
async def list_audit_logs(
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by user UUID"),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. AUTH_LOGIN_SUCCESS)"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, FAILURE, BLOCKED, ALERT)"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Page limit (max 100)"),
    admin: User = Depends(require_admin_or_developer),
    db: Session = Depends(get_db),
):
    result: AuditLogListResponse = AuditLogService.list_audit_logs(
        db=db,
        target_user_id=user_id,
        event_type=event_type,
        status_filter=status,
        skip=skip,
        limit=limit,
    )
    return res.ok(
        message="Audit logs retrieved successfully.",
        data=result.model_dump(mode="json"),
    )
