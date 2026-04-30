"""Add auth tables (users, refresh_tokens, oauth_states, oauth_tokens)

Revision ID: 0002_auth_tables
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_auth_tables"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("github_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="analyst"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_users_github_id", "users", ["github_id"])
    op.create_index("idx_users_github_id", "users", ["github_id"])

    # ── refresh_tokens ────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_unique_constraint("uq_refresh_tokens_hash", "refresh_tokens", ["token_hash"])
    op.create_index("idx_refresh_tokens_hash", "refresh_tokens", ["token_hash"])

    # ── oauth_states (temporary, for PKCE flow) ───────────────────────────
    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(), primary_key=True),
        sa.Column("code_verifier", sa.String(), nullable=False),
        sa.Column("cli_callback", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── oauth_tokens (temporary, for CLI polling) ─────────────────────────
    op.create_table(
        "oauth_tokens",
        sa.Column("state", sa.String(), primary_key=True),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_states")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
