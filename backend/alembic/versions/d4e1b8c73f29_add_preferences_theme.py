"""Add user_preferences.theme

Light, dark, or follow the operating system. Stored per account so the choice
follows the user between machines; the browser keeps a copy so the first paint
does not flash the wrong theme.

Revision ID: d4e1b8c73f29
Revises: c7a2e4b91d38
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e1b8c73f29'
down_revision: str | None = 'c7a2e4b91d38'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'user_preferences',
        sa.Column(
            'theme', sa.String(length=10), nullable=False, server_default='system',
        ),
    )


def downgrade() -> None:
    op.drop_column('user_preferences', 'theme')
