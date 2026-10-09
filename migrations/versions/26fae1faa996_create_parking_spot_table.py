"""Create the initial parking spot table.

Revision ID: 26fae1faa996
Revises:
Create Date: 2026-10-08 13:52:08.969692
"""

from alembic import op
import sqlalchemy as sa


revision = "26fae1faa996"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parking_spot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("spot_number", sa.String(length=10), nullable=False),
        sa.Column("is_occupied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("spot_number"),
    )


def downgrade():
    op.drop_table("parking_spot")
