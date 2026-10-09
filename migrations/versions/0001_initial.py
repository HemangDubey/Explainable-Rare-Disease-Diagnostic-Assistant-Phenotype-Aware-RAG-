"""initial schema: users, sessions, cases, scenarios, reports, drafts

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(80)),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("failed_attempts", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_login_at", sa.DateTime),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime),
    )
    op.create_index("ix_auth_sessions_user", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires", "auth_sessions", ["absolute_expires_at"])
    op.create_table(
        "cases",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("data", JSONT, nullable=False),
    )
    op.create_index("ix_cases_owner_created", "cases", ["owner_id", "created_at"])
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("case_id", sa.String(32), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("operations", JSONT, nullable=False),
        sa.Column("result", JSONT, nullable=False),
    )
    op.create_index("ix_scenarios_case", "scenarios", ["case_id"])
    op.create_index("ix_scenarios_owner", "scenarios", ["owner_id"])
    op.create_table(
        "reports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("case_id", sa.String(32), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("data", JSONT, nullable=False),
        sa.Column("export_count", sa.Integer, nullable=False),
        sa.Column("last_exported_at", sa.DateTime),
    )
    op.create_index("ix_reports_case", "reports", ["case_id"])
    op.create_index("ix_reports_owner", "reports", ["owner_id"])
    op.create_table(
        "drafts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("data", JSONT, nullable=False),
    )
    op.create_index("ix_drafts_owner_updated", "drafts", ["owner_id", "updated_at"])


def downgrade():
    for t in ("drafts", "reports", "scenarios", "cases", "auth_sessions", "users"):
        op.drop_table(t)
