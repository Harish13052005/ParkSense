from app.config import _database_uri


def test_database_defaults_to_target_mysql_database(monkeypatch):
    for name in (
        "DATABASE_URL",
        "MYSQL_HOST",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_PORT",
        "MYSQL_DB",
        "PARKSENSE_ALLOW_SQLITE",
    ):
        monkeypatch.delenv(name, raising=False)

    assert _database_uri() == (
        "mysql+pymysql://parksense_user:@localhost:3306/parksense_db"
    )


def test_mysql_settings_override_stale_sqlite_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    monkeypatch.setenv("MYSQL_HOST", "mysql.example")
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_PORT", raising=False)
    monkeypatch.delenv("MYSQL_DB", raising=False)

    assert _database_uri() == (
        "mysql+pymysql://parksense_user:@mysql.example:3306/parksense_db"
    )


def test_sqlite_database_url_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    monkeypatch.delenv("MYSQL_HOST", raising=False)
    monkeypatch.delenv("PARKSENSE_ALLOW_SQLITE", raising=False)

    try:
        _database_uri()
    except RuntimeError as error:
        assert "PARKSENSE_ALLOW_SQLITE=1" in str(error)
    else:
        raise AssertionError("SQLite DATABASE_URL should require an explicit opt-in")


def test_mysql_is_used_when_host_is_explicitly_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_USER", "parking")
    monkeypatch.setenv("MYSQL_PASSWORD", "pass@word")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DB", "parking_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _database_uri() == (
        "mysql+pymysql://parking:pass%40word@localhost:3307/parking_db"
    )
