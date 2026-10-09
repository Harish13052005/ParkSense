from app.config import _database_uri


def test_database_defaults_to_local_sqlite(monkeypatch):
    for name in (
        "DATABASE_URL",
        "MYSQL_HOST",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_PORT",
        "MYSQL_DB",
    ):
        monkeypatch.delenv(name, raising=False)

    assert _database_uri() == "sqlite:///parksense.db"


def test_database_url_takes_precedence_over_mysql_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    monkeypatch.setenv("MYSQL_HOST", "mysql.example")

    assert _database_uri() == "sqlite:///custom.db"


def test_mysql_is_used_when_host_is_explicitly_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_USER", "parking")
    monkeypatch.setenv("MYSQL_PASSWORD", "pass@word")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DB", "parking_db")

    assert _database_uri() == (
        "mysql+pymysql://parking:pass%40word@localhost:3307/parking_db"
    )
