"""Initial profiles table

Revision ID: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgcrypto for gen_random_uuid (UUID v4 fallback)
    # For UUID v7 we generate in the seed script via Python uuid_utils
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("gender", sa.String(), nullable=False),
        sa.Column("gender_probability", sa.Float(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("age_group", sa.String(), nullable=False),
        sa.Column("country_id", sa.String(2), nullable=False),
        sa.Column("country_name", sa.String(), nullable=False),
        sa.Column("country_probability", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Unique constraint on name
    op.create_unique_constraint("uq_profiles_name", "profiles", ["name"])

    # Indexes for fast filtering (no full-table scans)
    op.create_index("idx_profiles_gender", "profiles", ["gender"])
    op.create_index("idx_profiles_age_group", "profiles", ["age_group"])
    op.create_index("idx_profiles_country_id", "profiles", ["country_id"])
    op.create_index("idx_profiles_age", "profiles", ["age"])
    op.create_index("idx_profiles_created_at", "profiles", ["created_at"])
    op.create_index("idx_profiles_gender_probability", "profiles", ["gender_probability"])


def downgrade() -> None:
    op.drop_table("profiles")
