"""Add embedding and chunking preferences

Revision ID: 4b6438d6b6a4
Revises: a31f784083b2
Create Date: 2026-10-18 11:19:17.765483
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '4b6438d6b6a4'
down_revision: str | None = 'a31f784083b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also proposed dropping ix_knowledge_fragments_fts. It
    # cannot reflect an expression index, so it reads the existing one as
    # spurious; dropping it would take full-text search down. Left alone.
    op.add_column('user_preferences', sa.Column('embedding_model', sa.String(length=120), nullable=True))
    op.add_column('user_preferences', sa.Column('embedding_dimensions', sa.Integer(), nullable=True))
    op.add_column('user_preferences', sa.Column('embedding_context_limit', sa.Integer(), nullable=True))
    op.add_column('user_preferences', sa.Column('chunk_target_tokens', sa.Integer(), nullable=True))
    op.add_column('user_preferences', sa.Column('chunk_overlap_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_preferences', 'chunk_overlap_tokens')
    op.drop_column('user_preferences', 'chunk_target_tokens')
    op.drop_column('user_preferences', 'embedding_context_limit')
    op.drop_column('user_preferences', 'embedding_dimensions')
    op.drop_column('user_preferences', 'embedding_model')
