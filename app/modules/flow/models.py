import uuid
from datetime import datetime
from sqlalchemy import Boolean, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.core import timezone as tz


class FlowDiagram(Base):
    __tablename__ = "flow_diagrams"

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
    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    thumbnail_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    locked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        onupdate=tz.now,
        nullable=False,
    )

    # Relationships
    project = relationship("Project", backref="flow_diagrams")
    creator = relationship("User", foreign_keys=[created_by])
    editor = relationship("User", foreign_keys=[updated_by])
    locked_by_user = relationship("User", foreign_keys=[locked_by_user_id])
    pages: Mapped[list["FlowPage"]] = relationship(
        "FlowPage",
        back_populates="diagram",
        cascade="all, delete-orphan",
        order_by="FlowPage.page_order",
    )


class FlowPage(Base):
    __tablename__ = "flow_pages"
    __table_args__ = (
        UniqueConstraint("diagram_id", "drawio_page_id", name="uq_flow_pages_diagram_drawio_page"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    diagram_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flow_diagrams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    drawio_page_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        default="Page-1",
        nullable=False,
    )
    xml_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    compressed_xml: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    background_color: Mapped[str] = mapped_column(
        String(7),
        default="#FFFFFF",
        nullable=False,
    )
    grid_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    grid_size: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )
    page_width: Mapped[int] = mapped_column(
        Integer,
        default=1050,
        nullable=False,
    )
    page_height: Mapped[int] = mapped_column(
        Integer,
        default=1485,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        onupdate=tz.now,
        nullable=False,
    )

    # Relationships
    diagram: Mapped["FlowDiagram"] = relationship("FlowDiagram", back_populates="pages")

    