import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.core.enums import InvitationStatus, OwnershipTransferStatus, ProjectRole
from app.core import timezone as tz
from app.modules.projects.models import ProjectMember


class ProjectInvitation(Base):
    __tablename__ = "project_invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inviter_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=ProjectRole.EDITOR.value,
        nullable=False,
    )
    invitation_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=InvitationStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        nullable=False,
    )

    # Relationships
    project = relationship("Project", backref="invitations")
    inviter = relationship("User", foreign_keys=[inviter_user_id])


class ProjectOwnershipTransfer(Base):
    __tablename__ = "project_ownership_transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nominee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=OwnershipTransferStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    project = relationship("Project", backref="ownership_transfers")
    current_owner = relationship("User", foreign_keys=[current_owner_id])
    nominee_user = relationship("User", foreign_keys=[nominee_user_id])

    @property
    def is_expired(self) -> bool:
        exp = tz.ensure_tz_aware(self.expires_at)
        return exp is not None and tz.now() >= exp



__all__ = ["ProjectInvitation", "ProjectMember", "ProjectOwnershipTransfer"]

