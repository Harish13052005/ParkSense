import os
import pytest
from app import create_app, db
from app.models import User, ParkingSpot
from flask_login import login_user

# ----------------------------------------------------------------------
# Create a fresh Flask app for each test session
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def app():
    # Use an in‑memory SQLite DB for speed (does not affect your real MySQL DB)
    os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    os.environ["SECRET_KEY"] = "testing-secret-key"

    app = create_app()
    app.config.update(
        TESTING=True,
        DEBUG=False,
        # Disable CSRF for API tests (you can enable it if you wish)
        WTF_CSRF_ENABLED=False,
    )
    with app.app_context():
        db.create_all()
        # Seed a default user for auth tests
        admin = User(username="admin", email="admin@example.com")
        admin.set_password("Secret123!")
        db.session.add(admin)
        db.session.commit()
    yield app

    # Teardown – drop all tables
    with app.app_context():
        db.session.remove()
        db.drop_all()


# ----------------------------------------------------------------------
# Provide a Flask test client (covers cookies, session, etc.)
# ----------------------------------------------------------------------
@pytest.fixture
def client(app):
    return app.test_client()


# ----------------------------------------------------------------------
# Provide a logged‑in client for protected endpoints
# ----------------------------------------------------------------------
@pytest.fixture
def auth_client(client, app):
    """Log in as the admin user and return a client that carries the session cookie."""
    login_resp = client.post(
        "/auth/login",
        data=dict(username="admin", password="Secret123!"),
        follow_redirects=True,
    )
    assert login_resp.status_code == 200
    return client