"""Add full-text search indexes

Keyword search is PostgreSQL's own full-text search, so the only thing
needed is a GIN index over the same expression the query uses. Without it
every search sequentially scans and re-tokenises every fragment.

`to_tsvector('english', ...)` is immutable when the configuration is a
literal, which is what makes an expression index possible here. The literal
must match the query exactly or the planner will not use the index.

Revision ID: f5a2c91d6e04
Revises: d4e1b8c73f29
"""
from alembic import op

revision = "f5a2c91d6e04"
down_revision = "d4e1b8c73f29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_knowledge_fragments_fts "
        "ON knowledge_fragments USING GIN (to_tsvector('english', content))"
    )
    # There is deliberately no matching index on the artifact side. Its
    # searchable text is a concatenation of the filename and the metadata
    # JSONB, and both `concat_ws` and a JSONB-to-text cast are STABLE rather
    # than IMMUTABLE, so PostgreSQL refuses them in an index expression. A
    # generated column would hit the same rule. The artifact table holds one
    # row per document rather than one per chunk, and the text involved is a
    # title and a few short lists, so the sequential scan is cheap; the
    # fragment index is where the cost actually was.


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_fragments_fts")
