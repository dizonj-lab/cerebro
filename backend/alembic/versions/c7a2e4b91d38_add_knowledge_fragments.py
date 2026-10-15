"""Add knowledge_fragments and fragment_embeddings

Fragments are chunks of a registered artifact's extracted text, each keeping
the source location it came from. Embeddings are float4[] rather than a
pgvector column: pgvector is not available in the target PostgreSQL, and
brute-force cosine over arrays is adequate at this scale.

Revision ID: c7a2e4b91d38
Revises: b3c9d1f47a52
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c7a2e4b91d38'
down_revision: str | None = 'b3c9d1f47a52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'knowledge_fragments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('source_location', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'artifact_id', 'content_sha256', name='uq_fragments_artifact_content',
        ),
    )
    op.create_index('ix_fragments_owner', 'knowledge_fragments', ['owner_id'])
    op.create_index(
        'ix_fragments_artifact_ordinal', 'knowledge_fragments', ['artifact_id', 'ordinal'],
    )

    op.create_table(
        'fragment_embeddings',
        sa.Column('fragment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('vector', postgresql.ARRAY(sa.REAL()), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['fragment_id'], ['knowledge_fragments.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('fragment_id'),
    )
    op.create_index(
        'ix_embeddings_owner_space', 'fragment_embeddings',
        ['owner_id', 'provider', 'model', 'dimensions'],
    )


def downgrade() -> None:
    op.drop_index('ix_embeddings_owner_space', table_name='fragment_embeddings')
    op.drop_table('fragment_embeddings')
    op.drop_index('ix_fragments_artifact_ordinal', table_name='knowledge_fragments')
    op.drop_index('ix_fragments_owner', table_name='knowledge_fragments')
    op.drop_table('knowledge_fragments')
