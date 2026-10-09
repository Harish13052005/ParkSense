from datetime import datetime, timedelta, timezone

from app import db
from app.models import ParkingSession, ParkingSpot, Reservation
from app.services.parking import loyalty_tier, parse_datetime


def register_vehicle(client, headers, number="ABC123", kind="4-WHEELER", employee=None):
    data = {"vehicle_number": number, "vehicle_type": kind}
    if employee:
        data["employee_code"] = employee
    response = client.post("/api/vehicles", headers=headers, json=data)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_vehicle_entry_allocates_nearest_compatible_bay_and_exit_calculates_fare(
    app, client, bearer_headers
):
    with app.app_context():
        db.session.add_all(
            [
                ParkingSpot(spot_number="FW-NEAR", vehicle_type="4-WHEELER", distance_from_entry=2),
                ParkingSpot(spot_number="FW-FAR", vehicle_type="4-WHEELER", distance_from_entry=20),
            ]
        )
        db.session.commit()

    employee = client.post(
        "/api/employees",
        headers=bearer_headers,
        json={
            "employee_code": "EMP-1",
            "full_name": "Park User",
            "exemption_percent": 50,
        },
    )
    assert employee.status_code == 201
    register_vehicle(client, bearer_headers, employee="EMP-1")

    entry = client.post(
        "/api/entry", headers=bearer_headers, json={"vehicle_number": "abc 123"}
    )
    assert entry.status_code == 201
    assert entry.get_json()["spot_number"] == "FW-NEAR"
    assert entry.get_json()["status"] == "ACTIVE"
    assert client.post(
        "/api/entry", headers=bearer_headers, json={"vehicle_number": "ABC123"}
    ).status_code == 400

    with app.app_context():
        session = db.session.get(ParkingSession, entry.get_json()["id"])
        session.entry_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=61)
        db.session.commit()

    exit_response = client.post(
        "/api/exit", headers=bearer_headers, json={"vehicle_number": "ABC123"}
    )
    assert exit_response.status_code == 200
    result = exit_response.get_json()
    assert result["duration_minutes"] == 61
    assert result["base_fare"] == "100.00"
    assert result["employee_discount"] == "50.00"
    assert result["tax_amount"] == "9.00"
    assert result["final_fare"] == "59.00"

    with app.app_context():
        assert db.session.get(ParkingSpot, 1).status == "AVAILABLE"
    history = client.get("/api/history", headers=bearer_headers)
    assert history.status_code == 200
    assert history.get_json()[0]["final_fare"] == "59.00"


def test_vehicle_type_and_availability_are_enforced(client, bearer_headers, app):
    with app.app_context():
        db.session.add(
            ParkingSpot(spot_number="TW-1", vehicle_type="2-WHEELER", distance_from_entry=1)
        )
        db.session.commit()
    register_vehicle(client, bearer_headers, number="CAR-1")
    result = client.post(
        "/api/entry", headers=bearer_headers, json={"vehicle_number": "CAR-1"}
    )
    assert result.status_code == 400
    assert "compatible" in result.get_json()["error"]

    invalid = client.post(
        "/api/vehicles",
        headers=bearer_headers,
        json={"vehicle_number": "BAD-1", "vehicle_type": "TRUCK"},
    )
    assert invalid.status_code == 400


def test_maintenance_bays_are_excluded_until_restored(client, bearer_headers, app):
    with app.app_context():
        spot = ParkingSpot(
            spot_number="FW-MAINT", vehicle_type="4-WHEELER", distance_from_entry=1
        )
        db.session.add(spot)
        db.session.commit()
        spot_id = spot.id
    blocked = client.patch(
        f"/api/spots/{spot_id}/status",
        headers=bearer_headers,
        json={"status": "MAINTENANCE"},
    )
    assert blocked.status_code == 200
    register_vehicle(client, bearer_headers, number="CAR-M")
    no_bay = client.post(
        "/api/entry", headers=bearer_headers, json={"vehicle_number": "CAR-M"}
    )
    assert no_bay.status_code == 400

    restored = client.patch(
        f"/api/spots/{spot_id}/status",
        headers=bearer_headers,
        json={"status": "AVAILABLE"},
    )
    assert restored.status_code == 200
    assert client.post(
        "/api/entry", headers=bearer_headers, json={"vehicle_number": "CAR-M"}
    ).status_code == 201


def test_local_reservation_times_and_configurable_loyalty_tiers(app):
    with app.app_context():
        app.config["PARKING_TIMEZONE"] = "Asia/Kolkata"
        local_time = parse_datetime("2026-10-08T12:00:00")
        offset_time = parse_datetime("2026-10-08T12:00:00+05:30")
        assert local_time == offset_time
        assert local_time == datetime(2026, 10, 8, 6, 30)
        assert loyalty_tier(0) == "New"
        assert loyalty_tier(9) == "Occasional"
        assert loyalty_tier(10) == "Regular"
        assert loyalty_tier(25) == "Frequent"
        assert loyalty_tier(50) == "Highly Frequent"


def test_reservations_prevent_overlap_require_payment_and_allow_reserved_checkin(
    app, client, bearer_headers
):
    with app.app_context():
        db.session.add(
            ParkingSpot(spot_number="FW-1", vehicle_type="4-WHEELER", distance_from_entry=1)
        )
        db.session.commit()
    register_vehicle(client, bearer_headers, number="CAR-1")
    register_vehicle(client, bearer_headers, number="CAR-2")
    starts_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    ends_at = starts_at + timedelta(hours=2)
    request_data = {
        "vehicle_number": "CAR-1",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }
    created = client.post(
        "/api/reservations", headers=bearer_headers, json=request_data
    )
    assert created.status_code == 201
    reservation_id = created.get_json()["id"]
    assert created.get_json()["status"] == "PENDING_PAYMENT"
    assert created.get_json()["estimated_fare"] == "118.00"

    conflict = client.post(
        "/api/reservations",
        headers=bearer_headers,
        json={**request_data, "vehicle_number": "CAR-2"},
    )
    assert conflict.status_code == 400
    assert "available" in conflict.get_json()["error"]

    unpaid_entry = client.post(
        "/api/entry",
        headers=bearer_headers,
        json={"vehicle_number": "CAR-1", "reservation_id": reservation_id},
    )
    assert unpaid_entry.status_code == 400
    paid = client.post(
        f"/api/reservations/{reservation_id}/confirm-payment",
        headers=bearer_headers,
    )
    assert paid.status_code == 200
    assert paid.get_json()["payment_status"] == "PAID"

    with app.app_context():
        reservation = db.session.get(Reservation, reservation_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        reservation.starts_at = now - timedelta(minutes=1)
        reservation.ends_at = now + timedelta(hours=1)
        db.session.commit()

    live_analytics = client.get("/api/analytics", headers=bearer_headers).get_json()
    assert live_analytics["slot_status_counts"]["RESERVED"] == 1

    entry = client.post(
        "/api/entry",
        headers=bearer_headers,
        json={"vehicle_number": "CAR-1", "reservation_id": reservation_id},
    )
    assert entry.status_code == 201
    assert entry.get_json()["spot_number"] == "FW-1"
    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        session = db.session.get(ParkingSession, entry.get_json()["id"])
        session.entry_time = now - timedelta(minutes=121)
        reservation = db.session.get(Reservation, reservation_id)
        reservation.ends_at = now - timedelta(minutes=31)
        db.session.commit()
    checkout = client.post(
        "/api/exit", headers=bearer_headers, json={"vehicle_number": "CAR-1"}
    )
    assert checkout.status_code == 200
    assert checkout.get_json()["prepaid_amount"] == "118.00"
    assert checkout.get_json()["amount_due"] == "59.00"
    assert checkout.get_json()["overstay_minutes"] >= 30
    assert client.get("/api/analytics", headers=bearer_headers).get_json()[
        "occupied_slots"
    ] == 0


def test_dashboard_renders_after_login(auth_client):
    dashboard = auth_client.get("/")
    assert b"Live facility dashboard" in dashboard.data
    assert b"Live parking-bay map" in dashboard.data
    assert b"Upcoming reservation demand" in dashboard.data
    assert b"Vehicle entry" in auth_client.get("/").data


def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"User login" in response.data
    assert b"Administrator login" in response.data
