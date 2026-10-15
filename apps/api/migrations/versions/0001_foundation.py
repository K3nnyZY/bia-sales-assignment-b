"""Establish the migration baseline; domain tables belong to later sprints.

Alembic creates and records its own version table transactionally.
"""

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
