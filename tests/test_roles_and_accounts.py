from datetime import datetime, timedelta, timezone

from app import db
from app.models import ParkingSpot, User, Vehicle


def create_customer(client):
    response = client.post(
        "/auth/register",
        data={
            "username": "driver",
            "email": "driver@example.com",
            "password": "DriverPass123!",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    return response


def test_landing_page_offers_distinct_admin_and_user_access(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"User login" in response.data
    assert b"Administrator login" in response.data
    assert client.get("/auth/user-login").status_code == 200
    assert client.get("/auth/admin-login").status_code == 200


def test_create_admin_command_provisions_only_an_admin_account(app):
    result = app.test_cli_runner().invoke(
        args=["create-admin"],
        input="cli-admin\ncli-admin@example.com\nCliPass123!\nCliPass123!\n",
    )
    assert result.exit_code == 0, result.output
    with app.app_context():
        admin = User.query.filter_by(username="cli-admin").one()
        assert admin.role == "ADMIN"


def test_set_admin_password_command_updates_existing_credentials(app):
    result = app.test_cli_runner().invoke(
        args=["set-admin-password", "admin"],
        input="NewSecurePass123!\nNewSecurePass123!\n",
    )
    assert result.exit_code == 0, result.output
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        assert admin.role == "ADMIN"
        assert admin.check_password("NewSecurePass123!")


def test_user_registration_cannot_create_an_admin_and_login_is_role_specific(
    app, client
):
    create_customer(client)
    with app.app_context():
        customer = User.query.filter_by(username="driver").one()
        assert customer.role == "CUSTOMER"

    rejected_admin_login = client.post(
        "/auth/admin-login",
        data={"username": "driver", "password": "DriverPass123!"},
    )
    assert rejected_admin_login.status_code == 302
    assert rejected_admin_login.headers["Location"].endswith("/auth/admin-login")
    assert client.post(
        "/auth/user-login",
        data={"username": "admin", "password": "Secret123!"},
    ).headers["Location"].endswith("/auth/user-login")


def test_customer_access_is_limited_to_their_own_account_and_admin_operations(
    app, client
):
    create_customer(client)
    login = client.post(
        "/auth/user-login",
        data={"username": "driver", "password": "DriverPass123!"},
    )
    assert login.headers["Location"].endswith("/account")

    denied_page = client.get("/spots")
    assert denied_page.headers["Location"].endswith("/account")
    denied_employees = client.get("/admin/employees")
    assert denied_employees.headers["Location"].endswith("/account")

    token = client.post(
        "/api/auth/token",
        json={"username": "driver", "password": "DriverPass123!"},
    ).get_json()["access_token"]
    denied_api = client.get(
        "/api/analytics", headers={"Authorization": f"Bearer {token}"}
    )
    assert denied_api.status_code == 401

    added_vehicle = client.post(
        "/account/vehicles/add",
        data={"vehicle_number": "USER-CAR", "vehicle_type": "4-WHEELER"},
        follow_redirects=True,
    )
    assert b"USER-CAR" in added_vehicle.data
    with app.app_context():
        vehicle = Vehicle.query.filter_by(vehicle_number="USER-CAR").one()
        assert vehicle.owner.username == "driver"


def test_customer_can_only_reserve_their_own_vehicle(app, client):
    create_customer(client)
    with app.app_context():
        customer = User.query.filter_by(username="driver").one()
        db.session.add(
            ParkingSpot(
                spot_number="USER-BAY",
                vehicle_type="4-WHEELER",
                distance_from_entry=1,
            )
        )
        db.session.add(
            Vehicle(
                vehicle_number="OTHER-CAR",
                vehicle_type="4-WHEELER",
            )
        )
        db.session.commit()
        user_id = customer.id

    client.post(
        "/auth/user-login",
        data={"username": "driver", "password": "DriverPass123!"},
    )
    unauthorized_reservation = client.post(
        "/account/reservations",
        data={
            "vehicle_number": "OTHER-CAR",
            "starts_at": (
                datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
            ).isoformat(),
            "ends_at": (
                datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1, hours=2)
            ).isoformat(),
        },
        follow_redirects=True,
    )
    assert b"Choose a vehicle registered to your account" in unauthorized_reservation.data

    client.post(
        "/account/vehicles/add",
        data={"vehicle_number": "OWN-CAR", "vehicle_type": "4-WHEELER"},
    )
    starts_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    reservation = client.post(
        "/account/reservations",
        data={
            "vehicle_number": "OWN-CAR",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
        },
        follow_redirects=True,
    )
    assert b"Reservation #" in reservation.data
    assert b"OWN-CAR" in reservation.data
    with app.app_context():
        assert db.session.get(User, user_id).vehicles[0].owner_id == user_id


def test_administrator_can_manage_employee_directory(auth_client):
    response = auth_client.get("/admin/employees")
    assert response.status_code == 200
    created = auth_client.post(
        "/admin/employees",
        data={
            "employee_code": "EMP-ADMIN",
            "full_name": "Facility Employee",
            "department": "Operations",
            "exemption_percent": "50",
        },
        follow_redirects=True,
    )
    assert b"EMP-ADMIN" in created.data
    assert auth_client.get("/").status_code == 200
