import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "d6a18f4c2b90_import_legacy_parking_records.py"
)
SPEC = importlib.util.spec_from_file_location("legacy_import_migration", MIGRATION_PATH)
legacy_import = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy_import)


def test_legacy_import_copies_rows_without_mutating_sources_or_duplicates():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE employee (id INTEGER PRIMARY KEY, employee_code VARCHAR(50) UNIQUE, "
            "full_name VARCHAR(100), department VARCHAR(100), is_active BOOLEAN, "
            "exemption_percent NUMERIC)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE vehicle (id INTEGER PRIMARY KEY, vehicle_number VARCHAR(20) UNIQUE, "
            "vehicle_type VARCHAR(12), employee_id INTEGER, created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE parking_spot (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "spot_number VARCHAR(20) UNIQUE, vehicle_type VARCHAR(12), "
            "distance_from_entry INTEGER, status VARCHAR(16), is_occupied BOOLEAN, "
            "created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, employee_id VARCHAR(50), "
            "full_name VARCHAR(100), department VARCHAR(100), email VARCHAR(150), "
            "is_active BOOLEAN, created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE vehicles (id INTEGER PRIMARY KEY, vehicle_number VARCHAR(20), "
            "vehicle_type VARCHAR(12), employee_id INTEGER, created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE parking_slots (id INTEGER PRIMARY KEY, parking_zone_id INTEGER, "
            "slot_number VARCHAR(20), vehicle_type VARCHAR(12), "
            "distance_from_entry INTEGER, status VARCHAR(20), created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "INSERT INTO employees VALUES "
            "(7, 'EMP-LEGACY', 'Legacy Employee', 'Operations', 'kept@example.invalid', "
            "1, '2026-01-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO vehicles VALUES "
            "(9, 'LEGACY-CAR', '4-WHEELER', 7, '2026-01-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO parking_spot "
            "(spot_number, vehicle_type, distance_from_entry, status, is_occupied, created_at) "
            "VALUES ('FW-001', '4-WHEELER', 1, 'AVAILABLE', 0, '2026-01-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO parking_slots VALUES "
            "(1, 1, 'FW-001', '4-WHEELER', 1, 'AVAILABLE', '2026-01-01'), "
            "(2, 1, 'FW-002', '4-WHEELER', 2, 'OCCUPIED', '2026-01-01')"
        )

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            legacy_import.upgrade()
            legacy_import.upgrade()

        assert connection.exec_driver_sql(
            "SELECT id, employee_code FROM employee"
        ).all() == [(7, "EMP-LEGACY")]
        assert connection.exec_driver_sql(
            "SELECT id, vehicle_number, employee_id FROM vehicle"
        ).all() == [(9, "LEGACY-CAR", 7)]
        assert connection.exec_driver_sql(
            "SELECT spot_number, is_occupied FROM parking_spot ORDER BY spot_number"
        ).all() == [("FW-001", 0), ("FW-002", 1)]
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM employees").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM vehicles").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM parking_slots").scalar_one() == 2

    engine.dispose()
