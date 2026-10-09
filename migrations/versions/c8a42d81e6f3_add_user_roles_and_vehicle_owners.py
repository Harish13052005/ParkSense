"""Add administrator/customer roles and vehicle ownership.

Revision ID: c8a42d81e6f3
Revises: a12d9c4e81f3
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "c8a42d81e6f3"
down_revision = "a12d9c4e81f3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                sa.String(length=16),
                nullable=False,
                server_default="CUSTOMER",
            )
        )
        batch_op.create_index("ix_user_role", ["role"], unique=False)
        batch_op.create_check_constraint(
            "ck_user_role", "role IN ('ADMIN', 'CUSTOMER')"
        )
    op.execute("UPDATE user SET role = 'ADMIN'")
    op.add_column("vehicle", sa.Column("owner_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("vehicle") as batch_op:
        batch_op.create_foreign_key(
            "fk_vehicle_owner_id_user", "user", ["owner_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_vehicle_owner_id", ["owner_id"], unique=False)


def downgrade():
    with op.batch_alter_table("vehicle") as batch_op:
        batch_op.drop_index("ix_vehicle_owner_id")
        batch_op.drop_constraint("fk_vehicle_owner_id_user", type_="foreignkey")
        batch_op.drop_column("owner_id")
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("ck_user_role", type_="check")
        batch_op.drop_index("ix_user_role")
        batch_op.drop_column("role")
