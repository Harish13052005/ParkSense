from dotenv import load_dotenv
from sqlalchemy import inspect, text

load_dotenv()

from app import create_app
from app.extensions import db


app = create_app()

with app.app_context():
    engine = db.engine
    url = engine.url
    print("\n--- ParkSense Database Diagnostics ---")
    print("Database dialect:", url.drivername)
    print("Database host:", url.host)
    print("Database port:", url.port)
    print("Configured database:", url.database)
    print("Username:", url.username)

    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT
                        DATABASE() AS db_name,
                        @@hostname AS mysql_host,
                        @@port AS mysql_port,
                        CURRENT_USER() AS db_user
                    """
                )
            )
            row = result.one()
            print("\nActual database connection:")
            print(dict(row._mapping))

            inspector = inspect(connection)
            tables = inspector.get_table_names()
            print("\nTables visible to Flask:")
            for table in tables:
                print("-", table)
                columns = inspector.get_columns(table)
                print(
                    "  columns:",
                    ", ".join(
                        f"{column['name']} ({column['type']})" for column in columns
                    ),
                )
                quoted_table = connection.dialect.identifier_preparer.quote(table)
                count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {quoted_table}")
                ).scalar_one()
                print("  rows:", count)

            if "alembic_version" in tables:
                revisions = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalars().all()
                print("\nRecorded migration revision(s):", revisions)

        print("\nConnection test: SUCCESS")
    except Exception as error:
        print("\nConnection test: FAILED")
        print("Error type:", type(error).__name__)
        print("Error details suppressed to protect connection configuration.")
