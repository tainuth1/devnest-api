"""
Audit Log Pydantic Schemas.
"""

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """Schema for returning audit log entries."""
    id: str
    event_type: str
    status: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    user_username: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated response envelope for audit log listings."""
    items: list[AuditLogResponse]
    total: int
    skip: int
    limit: int
