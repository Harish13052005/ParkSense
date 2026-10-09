import os
from urllib.parse import quote_plus


def _database_uri() -> str:
    mysql_host = os.getenv("MYSQL_HOST")
    if mysql_host:
        username = quote_plus(os.getenv("MYSQL_USER", "parksense_user"))
        password = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
        port = os.getenv("MYSQL_PORT", "3306")
        database = os.getenv("MYSQL_DB", "parksense_db")
        return f"mysql+pymysql://{username}:{password}@{mysql_host}:{port}/{database}"

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.lower().startswith("sqlite") and os.getenv(
            "PARKSENSE_ALLOW_SQLITE", ""
        ).lower() not in {"1", "true", "yes"}:
            raise RuntimeError(
                "SQLite DATABASE_URL is disabled by default. Configure MYSQL_HOST "
                "and MySQL credentials, or set PARKSENSE_ALLOW_SQLITE=1 for "
                "intentional local SQLite use."
            )
        return database_url

    username = quote_plus(os.getenv("MYSQL_USER", "parksense_user"))
    password = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DB", "parksense_db")
    return (
        f"mysql+pymysql://{username}:{password}@localhost:{port}/{database}"
    )


class Config:
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "parksense-development-secret-key"
    )
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    LOGIN_DISABLED = False

    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY",
        "jwt-development-secret-key",
    )
    JWT_ALGORITHM = "HS256"
    JWT_EXP_DELTA_SECONDS = 3600
    PARKING_TIMEZONE = os.getenv("PARKING_TIMEZONE", "UTC")
    PARKING_HOURLY_RATES = {
        "2-WHEELER": 20,
        "3-WHEELER": 30,
        "4-WHEELER": 50,
    }
    PARKING_TAX_PERCENT = 18
    EMPLOYEE_EXEMPTION_PERCENT = 100
    LOYALTY_DISCOUNTS = {10: 5, 25: 10, 50: 15}
