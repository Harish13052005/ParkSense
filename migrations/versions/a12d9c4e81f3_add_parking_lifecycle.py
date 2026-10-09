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


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_table(table_name, required_columns, create):
    inspector = _inspector()
    if table_name not in inspector.get_table_names():
        create()
        return
    present = {column["name"] for column in inspector.get_columns(table_name)}
    missing = set(required_columns) - present
    if missing:
        raise RuntimeError(
            f"Existing {table_name!r} table is incomplete; missing columns: "
            + ", ".join(sorted(missing))
        )


def _ensure_index(table_name, name, columns, unique=False):
    existing = {index["name"] for index in _inspector().get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)


def _create_employee():
    op.create_table(
        "employee",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_code", sa.String(length=50), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("department", sa.String(length=100)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exemption_percent", sa.Numeric(5, 2)),
    )


def _create_vehicle():
    op.create_table(
        "vehicle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_number", sa.String(length=20), nullable=False),
        sa.Column("vehicle_type", sa.String(length=12), nullable=False),
        sa.Column("employee_id", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employee.id"],
            name="fk_app_vehicle_employee",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "vehicle_type IN ('2-WHEELER', '3-WHEELER', '4-WHEELER')",
            name="ck_vehicle_type",
        ),
    )


def _create_reservation():
    op.create_table(
        "reservation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("parking_spot_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("estimated_fare", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "payment_status", sa.String(length=10), nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False,
            server_default="PENDING_PAYMENT",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicle.id"],
            name="fk_reservation_vehicle", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parking_spot_id"], ["parking_spot.id"],
            name="fk_reservation_spot", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "payment_status IN ('PENDING', 'PAID', 'REFUNDED')",
            name="ck_reservation_payment_status",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_PAYMENT', 'CONFIRMED', 'CHECKED_IN', "
            "'COMPLETED', 'CANCELLED')",
            name="ck_reservation_status",
        ),
    )


def _create_parking_session():
    op.create_table(
        "parking_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("parking_spot_id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer()),
        sa.Column(
            "entry_time", sa.DateTime(), nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("exit_time", sa.DateTime()),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("base_fare", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column(
            "employee_discount", sa.Numeric(10, 2), nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "loyalty_discount", sa.Numeric(10, 2), nullable=False,
            server_default="0.00",
        ),
        sa.Column("tax_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("final_fare", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column(
            "prepaid_amount", sa.Numeric(10, 2), nullable=False,
            server_default="0.00",
        ),
        sa.Column("amount_due", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("overstay_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicle.id"],
            name="fk_session_vehicle", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parking_spot_id"], ["parking_spot.id"],
            name="fk_session_spot", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["reservation.id"],
            name="fk_session_reservation", ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')",
            name="ck_parking_session_status",
        ),
    )


def upgrade():
    inspector = _inspector()
    tables = set(inspector.get_table_names())

    if "user" not in tables:
        raise RuntimeError("The user table is required before the parking lifecycle migration.")
    user_columns = {column["name"]: column for column in inspector.get_columns("user")}
    password_type = user_columns.get("password_hash", {}).get("type")
    if password_type is None:
        raise RuntimeError("The user table is missing password_hash.")
    if getattr(password_type, "length", None) != 255:
        with op.batch_alter_table("user") as batch_op:
            batch_op.alter_column(
                "password_hash",
                existing_type=password_type,
                type_=sa.String(length=255),
                existing_nullable=False,
                nullable=False,
            )

    tables = set(_inspector().get_table_names())
    if "parking_spot" not in tables:
        raise RuntimeError("The parking_spot table is required before the lifecycle migration.")
    spot_columns = {
        column["name"]: column
        for column in _inspector().get_columns("parking_spot")
    }
    if "spot_number" not in spot_columns:
        raise RuntimeError("The parking_spot table is missing spot_number.")
    if getattr(spot_columns["spot_number"]["type"], "length", None) != 20:
        with op.batch_alter_table("parking_spot") as batch_op:
            batch_op.alter_column(
                "spot_number",
                existing_type=spot_columns["spot_number"]["type"],
                type_=sa.String(length=20),
                existing_nullable=False,
                nullable=False,
            )

    spot_columns = {column["name"] for column in _inspector().get_columns("parking_spot")}
    if "vehicle_type" not in spot_columns:
        op.add_column(
            "parking_spot",
            sa.Column(
                "vehicle_type", sa.String(length=12), nullable=False,
                server_default="4-WHEELER",
            ),
        )
    spot_columns = {column["name"] for column in _inspector().get_columns("parking_spot")}
    if "distance_from_entry" not in spot_columns:
        op.add_column(
            "parking_spot",
            sa.Column(
                "distance_from_entry", sa.Integer(), nullable=False,
                server_default="0",
            ),
        )
    spot_columns = {column["name"] for column in _inspector().get_columns("parking_spot")}
    if "status" not in spot_columns:
        op.add_column(
            "parking_spot",
            sa.Column(
                "status", sa.String(length=16), nullable=False,
                server_default="AVAILABLE",
            ),
        )
    spot_columns = {column["name"] for column in _inspector().get_columns("parking_spot")}
    if "created_at" not in spot_columns:
        op.add_column(
            "parking_spot",
            sa.Column(
                "created_at", sa.DateTime(), nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )

    op.execute(
        "UPDATE parking_spot SET status = 'OCCUPIED' "
        "WHERE is_occupied = 1 AND status <> 'OCCUPIED'"
    )
    check_names = {
        item["name"] for item in _inspector().get_check_constraints("parking_spot")
    }
    if "ck_spot_vehicle_type" not in check_names:
        with op.batch_alter_table("parking_spot") as batch_op:
            batch_op.create_check_constraint(
                "ck_spot_vehicle_type",
                "vehicle_type IN ('2-WHEELER', '3-WHEELER', '4-WHEELER')",
            )
    check_names = {
        item["name"] for item in _inspector().get_check_constraints("parking_spot")
    }
    if "ck_spot_status" not in check_names:
        with op.batch_alter_table("parking_spot") as batch_op:
            batch_op.create_check_constraint(
                "ck_spot_status",
                "status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'MAINTENANCE', 'BLOCKED')",
            )
    _ensure_index("parking_spot", "ix_parking_spot_status", ["status"])

    _ensure_table(
        "employee",
        {"id", "employee_code", "full_name", "department", "is_active", "exemption_percent"},
        _create_employee,
    )
    _ensure_index(
        "employee", "ix_employee_employee_code", ["employee_code"], unique=True
    )
    _ensure_table(
        "vehicle",
        {"id", "vehicle_number", "vehicle_type", "employee_id", "created_at"},
        _create_vehicle,
    )
    _ensure_index(
        "vehicle", "ix_vehicle_vehicle_number", ["vehicle_number"], unique=True
    )

    _ensure_table(
        "reservation",
        {
            "id", "vehicle_id", "parking_spot_id", "starts_at", "ends_at",
            "estimated_fare", "payment_status", "status", "created_at",
        },
        _create_reservation,
    )
    for name, column in (
        ("ix_reservation_starts_at", "starts_at"),
        ("ix_reservation_ends_at", "ends_at"),
        ("ix_reservation_status", "status"),
    ):
        _ensure_index("reservation", name, [column])

    _ensure_table(
        "parking_session",
        {
            "id", "vehicle_id", "parking_spot_id", "reservation_id", "entry_time",
            "exit_time", "duration_minutes", "base_fare", "employee_discount",
            "loyalty_discount", "tax_amount", "final_fare", "prepaid_amount",
            "amount_due", "overstay_minutes", "status",
        },
        _create_parking_session,
    )
    for name, column in (
        ("ix_parking_session_entry_time", "entry_time"),
        ("ix_parking_session_exit_time", "exit_time"),
        ("ix_parking_session_status", "status"),
    ):
        _ensure_index("parking_session", name, [column])


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
