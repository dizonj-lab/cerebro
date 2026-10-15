"""Add artifacts.extraction

Summary of deterministic text extraction: which adapter ran, how much it
found, and the object-store key of the full block-level result. Existing
rows get an empty object — they were text artifacts whose bytes are their
own extracted text, and `preview_text` reads them directly.

Revision ID: b3c9d1f47a52
Revises: e0b617a276f1
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'b3c9d1f47a52'
down_revision: str | None = 'e0b617a276f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'artifacts',
        sa.Column(
            'extraction',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column('artifacts', 'extraction')
