"""create_flow_diagrams_and_pages

Revision ID: 008_flow_diagrams
Revises: 007_project_ownership_transfers
Create Date: 2026-10-13 00:00:00.000000

Creates flow_diagrams, flow_pages, and flow_custom_libraries tables
for Phase 6: System Flow Designer (Draw.io Integration).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_flow_diagrams"
down_revision: Union[str, None] = "007_project_ownership_transfers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flow_diagrams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "locked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_flow_diagrams_project_id"), "flow_diagrams", ["project_id"], unique=False)
    op.create_index(op.f("ix_flow_diagrams_locked_by_user_id"), "flow_diagrams", ["locked_by_user_id"], unique=False)
    op.create_index(op.f("ix_flow_diagrams_created_by"), "flow_diagrams", ["created_by"], unique=False)
    op.create_index(op.f("ix_flow_diagrams_updated_by"), "flow_diagrams", ["updated_by"], unique=False)

    op.create_table(
        "flow_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "diagram_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flow_diagrams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drawio_page_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, server_default="Page-1"),
        sa.Column("xml_content", sa.Text(), nullable=False),
        sa.Column("compressed_xml", sa.Text(), nullable=True),
        sa.Column("background_color", sa.String(length=7), nullable=False, server_default="#FFFFFF"),
        sa.Column("grid_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("grid_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("page_width", sa.Integer(), nullable=False, server_default="1050"),
        sa.Column("page_height", sa.Integer(), nullable=False, server_default="1485"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("diagram_id", "drawio_page_id", name="uq_flow_pages_diagram_drawio_page"),
    )
    op.create_index(op.f("ix_flow_pages_diagram_id"), "flow_pages", ["diagram_id"], unique=False)

    op.create_table(
        "flow_custom_libraries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("xml_data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_flow_custom_libraries_project_id"), "flow_custom_libraries", ["project_id"], unique=False)
    op.create_index(op.f("ix_flow_custom_libraries_user_id"), "flow_custom_libraries", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_flow_custom_libraries_user_id"), table_name="flow_custom_libraries")
    op.drop_index(op.f("ix_flow_custom_libraries_project_id"), table_name="flow_custom_libraries")
    op.drop_table("flow_custom_libraries")

    op.drop_index(op.f("ix_flow_pages_diagram_id"), table_name="flow_pages")
    op.drop_table("flow_pages")

    op.drop_index(op.f("ix_flow_diagrams_updated_by"), table_name="flow_diagrams")
    op.drop_index(op.f("ix_flow_diagrams_created_by"), table_name="flow_diagrams")
    op.drop_index(op.f("ix_flow_diagrams_locked_by_user_id"), table_name="flow_diagrams")
    op.drop_index(op.f("ix_flow_diagrams_project_id"), table_name="flow_diagrams")
    op.drop_table("flow_diagrams")
