"""Add vehicle, employee, session, and reservation workflows.

Revision ID: a12d9c4e81f3
Revises: 773104daa8d1
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "a12d9c4e81f3"
down_revision = "773104daa8d1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=128),
            type_=sa.String(length=255),
            existing_nullable=False,
            nullable=False,
        )
    with op.batch_alter_table("parking_spot") as batch_op:
        batch_op.alter_column(
            "spot_number",
            existing_type=sa.String(length=10),
            type_=sa.String(length=20),
            existing_nullable=False,
            nullable=False,
        )
    op.add_column(
        "parking_spot",
        sa.Column(
            "vehicle_type", sa.String(length=12), nullable=False, server_default="4-WHEELER"
        ),
    )
    op.add_column(
        "parking_spot",
        sa.Column("distance_from_entry", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "parking_spot",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="AVAILABLE"),
    )
    op.add_column(
        "parking_spot",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.execute(
        "UPDATE parking_spot SET status = 'OCCUPIED' WHERE is_occupied = 1"
    )
    with op.batch_alter_table("parking_spot") as batch_op:
        batch_op.create_check_constraint(
            "ck_spot_vehicle_type",
            "vehicle_type IN ('2-WHEELER', '3-WHEELER', '4-WHEELER')",
        )
        batch_op.create_check_constraint(
            "ck_spot_status",
            "status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'MAINTENANCE', 'BLOCKED')",
        )
    op.create_index("ix_parking_spot_status", "parking_spot", ["status"])

    op.create_table(
        "employee",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_code", sa.String(length=50), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("department", sa.String(length=100)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exemption_percent", sa.Numeric(5, 2)),
    )
    op.create_index("ix_employee_employee_code", "employee", ["employee_code"], unique=True)

    op.create_table(
        "vehicle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_number", sa.String(length=20), nullable=False),
        sa.Column("vehicle_type", sa.String(length=12), nullable=False),
        sa.Column("employee_id", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employee.id"], name="fk_vehicle_employee", ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "vehicle_type IN ('2-WHEELER', '3-WHEELER', '4-WHEELER')",
            name="ck_vehicle_type",
        ),
    )
    op.create_index(
        "ix_vehicle_vehicle_number", "vehicle", ["vehicle_number"], unique=True
    )

    op.create_table(
        "reservation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("parking_spot_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("estimated_fare", sa.Numeric(10, 2), nullable=False),
        sa.Column("payment_status", sa.String(length=10), nullable=False, server_default="PENDING"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING_PAYMENT"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicle.id"], name="fk_reservation_vehicle", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parking_spot_id"],
            ["parking_spot.id"],
            name="fk_reservation_spot",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "payment_status IN ('PENDING', 'PAID', 'REFUNDED')",
            name="ck_reservation_payment_status",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_PAYMENT', 'CONFIRMED', 'CHECKED_IN', 'COMPLETED', 'CANCELLED')",
            name="ck_reservation_status",
        ),
    )
    op.create_index("ix_reservation_starts_at", "reservation", ["starts_at"])
    op.create_index("ix_reservation_ends_at", "reservation", ["ends_at"])
    op.create_index("ix_reservation_status", "reservation", ["status"])

    op.create_table(
        "parking_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("parking_spot_id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer()),
        sa.Column(
            "entry_time", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column("exit_time", sa.DateTime()),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("base_fare", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column(
            "employee_discount", sa.Numeric(10, 2), nullable=False, server_default="0.00"
        ),
        sa.Column(
            "loyalty_discount", sa.Numeric(10, 2), nullable=False, server_default="0.00"
        ),
        sa.Column("tax_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("final_fare", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("prepaid_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("amount_due", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("overstay_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicle.id"], name="fk_session_vehicle", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parking_spot_id"],
            ["parking_spot.id"],
            name="fk_session_spot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservation.id"],
            name="fk_session_reservation",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')",
            name="ck_parking_session_status",
        ),
    )
    op.create_index("ix_parking_session_entry_time", "parking_session", ["entry_time"])
    op.create_index("ix_parking_session_exit_time", "parking_session", ["exit_time"])
    op.create_index("ix_parking_session_status", "parking_session", ["status"])


def downgrade():
    op.drop_index("ix_parking_session_status", table_name="parking_session")
    op.drop_index("ix_parking_session_exit_time", table_name="parking_session")
    op.drop_index("ix_parking_session_entry_time", table_name="parking_session")
    op.drop_table("parking_session")
    op.drop_index("ix_reservation_status", table_name="reservation")
    op.drop_index("ix_reservation_ends_at", table_name="reservation")
    op.drop_index("ix_reservation_starts_at", table_name="reservation")
    op.drop_table("reservation")
    op.drop_index("ix_vehicle_vehicle_number", table_name="vehicle")
    op.drop_table("vehicle")
    op.drop_index("ix_employee_employee_code", table_name="employee")
    op.drop_table("employee")
    op.drop_index("ix_parking_spot_status", table_name="parking_spot")
    with op.batch_alter_table("parking_spot") as batch_op:
        batch_op.drop_constraint("ck_spot_status", type_="check")
        batch_op.drop_constraint("ck_spot_vehicle_type", type_="check")
        batch_op.drop_column("created_at")
        batch_op.drop_column("status")
        batch_op.drop_column("distance_from_entry")
        batch_op.drop_column("vehicle_type")
        batch_op.alter_column(
            "spot_number",
            existing_type=sa.String(length=20),
            type_=sa.String(length=10),
            existing_nullable=False,
            nullable=False,
        )
