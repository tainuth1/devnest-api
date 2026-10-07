import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON

from app.database import Base
from app.core import timezone as tz
from app.core.enums import NotificationActionStatus


class Notification(Base):
    """
    Persistent notification entity.
    Stores user in-app notifications for collaboration invitations,
    ownership transfers, backup snapshots, system alerts, and AI updates.
    """
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    # Approach 1: Dedicated top-level column for primary navigation link
    link_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    # Contextual data payload for action buttons (e.g. tokens, roles, IDs)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    action_status: Mapped[str | None] = mapped_column(
        String(20),
        default=NotificationActionStatus.PENDING.value,
        nullable=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        nullable=False,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="notifications")
    actor = relationship("User", foreign_keys=[actor_id])
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("ix_notifications_user_inbox", "user_id", "is_read", "created_at"),
    )
