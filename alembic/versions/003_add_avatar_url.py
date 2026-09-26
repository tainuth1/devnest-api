"""add_avatar_url_to_users

Revision ID: 003_add_avatar_url
Revises: 002_session_auth
Create Date: 2026-09-26 00:00:00.000000

Adds an optional avatar_url column to the users table for storing
a URL pointing to the user's profile image.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_add_avatar_url"
down_revision: Union[str, None] = "002_session_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
