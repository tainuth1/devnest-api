"""drop_flow_custom_libraries

Revision ID: 009_drop_flow_custom_libraries
Revises: 008_flow_diagrams
Create Date: 2026-10-13 20:30:00.000000

Drops the unused flow_custom_libraries table as custom stencils
have been replaced by native Draw.io libraries.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_drop_flow_custom_libraries"
down_revision: Union[str, None] = "008_flow_diagrams"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_flow_custom_libraries_user_id"), table_name="flow_custom_libraries")
    op.drop_index(op.f("ix_flow_custom_libraries_project_id"), table_name="flow_custom_libraries")
    op.drop_table("flow_custom_libraries")


def downgrade() -> None:
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
