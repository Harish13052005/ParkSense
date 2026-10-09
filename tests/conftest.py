import pytest

from app import create_app, db
from app.config import Config
from app.models import User


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SECRET_KEY = "test-secret-key-with-more-than-thirty-two-bytes"
    JWT_SECRET_KEY = "test-jwt-secret-key-with-more-than-thirty-two-bytes"
    WTF_CSRF_ENABLED = False
    PARKING_TIMEZONE = "UTC"
    PARKING_HOURLY_RATES = {"2-WHEELER": 20, "3-WHEELER": 30, "4-WHEELER": 50}
    PARKING_TAX_PERCENT = 18
    EMPLOYEE_EXEMPTION_PERCENT = 100
    LOYALTY_DISCOUNTS = {10: 5, 25: 10, 50: 15}


@pytest.fixture
def app():
    application = create_app(TestingConfig)
    with application.app_context():
        db.create_all()
        admin = User(username="admin", email="admin@example.com", role="ADMIN")
        admin.set_password("Secret123!")
        db.session.add(admin)
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    authenticated_client = app.test_client()
    response = authenticated_client.post(
        "/auth/admin-login",
        data={"username": "admin", "password": "Secret123!"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return authenticated_client


@pytest.fixture
def bearer_headers(client):
    response = client.post(
        "/api/auth/token",
        json={"username": "admin", "password": "Secret123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}
