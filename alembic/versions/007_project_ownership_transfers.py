"""create_project_ownership_transfers

Revision ID: 007_project_ownership_transfers
Revises: 006_notifications
Create Date: 2026-10-08 00:00:00.000000

Creates the project_ownership_transfers table for Phase 5:
Project Ownership Transfer Handshake (BR-TRANS-01 to BR-TRANS-04).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_project_ownership_transfers"
down_revision: Union[str, None] = "006_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_ownership_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "current_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "nominee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "initiated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "responded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_project_ownership_transfers_project_id"),
        "project_ownership_transfers",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_ownership_transfers_current_owner_id"),
        "project_ownership_transfers",
        ["current_owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_ownership_transfers_nominee_user_id"),
        "project_ownership_transfers",
        ["nominee_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_ownership_transfers_status"),
        "project_ownership_transfers",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_project_ownership_transfers_status"),
        table_name="project_ownership_transfers",
    )
    op.drop_index(
        op.f("ix_project_ownership_transfers_nominee_user_id"),
        table_name="project_ownership_transfers",
    )
    op.drop_index(
        op.f("ix_project_ownership_transfers_current_owner_id"),
        table_name="project_ownership_transfers",
    )
    op.drop_index(
        op.f("ix_project_ownership_transfers_project_id"),
        table_name="project_ownership_transfers",
    )
    op.drop_table("project_ownership_transfers")
