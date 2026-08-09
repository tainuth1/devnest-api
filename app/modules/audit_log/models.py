"""
Audit Log database model.

Stores security audit events in PostgreSQL database with relationship to User.
"""

import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.core import timezone as tz

if TYPE_CHECKING:
    from app.modules.auth.models import User


class AuditLog(Base):
    """
    Persisted record of security audit events in PostgreSQL.

    Has a foreign key relationship to User with SET NULL on deletion,
    so historical audit events remain even if a user account is removed.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Event Identifier (e.g. AUTH_LOGIN_SUCCESS, HONEYPOT_TRIGGERED)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Event Status (SUCCESS, FAILURE, BLOCKED, ALERT)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # FK Relationship to User (SET NULL on delete to preserve audit history)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Request & Client Metadata
    client_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Structured Sanitized Details Metadata (JSON)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Event Timestamp (uses configured Cambodia timezone, you can also change it in your .env configuration: APP_TIMEZONE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        nullable=False,
        index=True,
    )

    # ORM Relationship to User model
    user: Mapped[Optional["User"]] = relationship("User", backref="audit_logs")

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} "
            f"event={self.event_type} "
            f"status={self.status} "
            f"user_id={self.user_id} "
            f"created_at={self.created_at}>"
        )
