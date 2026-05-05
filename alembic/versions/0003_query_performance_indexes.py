"""Composite index for common filter combinations (country + gender + age).

Revision ID: 0003_query_performance
Revises: 0002_auth_tables
"""

from alembic import op

revision = "0003_query_performance"
down_revision = "0002_auth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Typical analyst queries: country + gender, often with age predicates.
    op.create_index(
        "idx_profiles_country_gender_age",
        "profiles",
        ["country_id", "gender", "age"],
    )


def downgrade() -> None:
    op.drop_index("idx_profiles_country_gender_age", table_name="profiles")
