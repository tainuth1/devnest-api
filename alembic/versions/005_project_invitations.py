"""create_project_invitations

Revision ID: 005_project_invitations
Revises: 004_projects
Create Date: 2026-10-07 00:00:00.000000

Creates the project_invitations table for Phase 4:
Collaboration, Members & RBAC.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_project_invitations"
down_revision: Union[str, None] = "004_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inviter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invitee_email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="EDITOR"),
        sa.Column("invitation_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        op.f("ix_project_invitations_project_id"),
        "project_invitations",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invitations_inviter_user_id"),
        "project_invitations",
        ["inviter_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invitations_invitee_email"),
        "project_invitations",
        ["invitee_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invitations_invitation_token_hash"),
        "project_invitations",
        ["invitation_token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_project_invitations_status"),
        "project_invitations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_invitations_status"), table_name="project_invitations")
    op.drop_index(
        op.f("ix_project_invitations_invitation_token_hash"),
        table_name="project_invitations",
    )
    op.drop_index(op.f("ix_project_invitations_invitee_email"), table_name="project_invitations")
    op.drop_index(
        op.f("ix_project_invitations_inviter_user_id"),
        table_name="project_invitations",
    )
    op.drop_index(op.f("ix_project_invitations_project_id"), table_name="project_invitations")
    op.drop_table("project_invitations")
