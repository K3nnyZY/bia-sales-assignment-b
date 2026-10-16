"""Expiring, revocable credentials for protected deployments."""

import sqlalchemy as sa
from alembic import op

revision = "0006_private_access_tokens"
down_revision = "0005_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "user_id", sa.String(80), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.CheckConstraint("expires_at > created_at", name="expiry"),
    )
    op.create_index("ix_access_tokens_user_id", "access_tokens", ["user_id"])


def downgrade():
    op.drop_table("access_tokens")
