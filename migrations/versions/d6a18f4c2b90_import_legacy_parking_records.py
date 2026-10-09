"""Import legacy plural tables into the application schema without removing them.

Revision ID: d6a18f4c2b90
Revises: c8a42d81e6f3
"""

from alembic import op
import sqlalchemy as sa


revision = "d6a18f4c2b90"
down_revision = "c8a42d81e6f3"
branch_labels = None
depends_on = None


def _copy_if_present(bind, tables, source, target, statement):
    if source not in tables:
        return
    if target not in tables:
        raise RuntimeError(
            f"Cannot import legacy table {source!r}: target table {target!r} is missing."
        )
    bind.execute(sa.text(statement))


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    _copy_if_present(
        bind,
        tables,
        "employees",
        "employee",
        """
        INSERT INTO employee
            (id, employee_code, full_name, department, is_active, exemption_percent)
        SELECT source.id, source.employee_id, source.full_name, source.department,
               source.is_active, NULL
        FROM employees AS source
        WHERE NOT EXISTS (
            SELECT 1 FROM employee AS target
            WHERE target.employee_code = source.employee_id
        )
        """,
    )
    _copy_if_present(
        bind,
        tables,
        "vehicles",
        "vehicle",
        """
        INSERT INTO vehicle
            (id, vehicle_number, vehicle_type, employee_id, created_at)
        SELECT source.id, source.vehicle_number, source.vehicle_type,
               source.employee_id, source.created_at
        FROM vehicles AS source
        WHERE NOT EXISTS (
            SELECT 1 FROM vehicle AS target
            WHERE target.vehicle_number = source.vehicle_number
        )
        """,
    )
    _copy_if_present(
        bind,
        tables,
        "parking_slots",
        "parking_spot",
        """
        INSERT INTO parking_spot
            (spot_number, vehicle_type, distance_from_entry, status,
             is_occupied, created_at)
        SELECT source.slot_number, source.vehicle_type, source.distance_from_entry,
               source.status,
               CASE WHEN source.status = 'OCCUPIED' THEN 1 ELSE 0 END,
               source.created_at
        FROM parking_slots AS source
        WHERE NOT EXISTS (
            SELECT 1 FROM parking_spot AS target
            WHERE target.spot_number = source.slot_number
        )
        """,
    )


def downgrade():
    # Source tables remain authoritative archives. Removing imported rows would
    # be destructive and is intentionally not part of this migration.
    pass
