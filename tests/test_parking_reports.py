import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO

from app import db
from app.models import ParkingSession, ParkingSpot, Reservation, Vehicle


def test_analytics_includes_upcoming_reservation_demand_and_bay_utilization(
    app, client, bearer_headers
):
    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        vehicle = Vehicle(vehicle_number="CAR-REPORT", vehicle_type="4-WHEELER")
        spot = ParkingSpot(
            spot_number="FW-REPORT",
            vehicle_type="4-WHEELER",
            distance_from_entry=1,
        )
        db.session.add_all([vehicle, spot])
        db.session.flush()
        db.session.add(
            ParkingSession(
                vehicle=vehicle,
                spot=spot,
                entry_time=now - timedelta(days=3),
                exit_time=now - timedelta(days=2),
                duration_minutes=1440,
                status="COMPLETED",
            )
        )
        reservation_start = now + timedelta(days=2)
        db.session.add(
            Reservation(
                vehicle=vehicle,
                spot=spot,
                starts_at=reservation_start,
                ends_at=reservation_start + timedelta(hours=2),
                estimated_fare=Decimal("118.00"),
                payment_status="PENDING",
                status="PENDING_PAYMENT",
            )
        )
        db.session.commit()

    response = client.get("/api/analytics", headers=bearer_headers)

    assert response.status_code == 200
    result = response.get_json()
    demand_day = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
    assert next(item for item in result["reservation_demand"] if item["date"] == demand_day)[
        "count"
    ] == 1
    bay = next(item for item in result["slot_utilization"] if item["spot_number"] == "FW-REPORT")
    assert bay["visits_30d"] == 1
    assert bay["utilization_percent"] == 3.33


def test_history_filters_and_csv_export_protect_spreadsheet_formulas(
    app, auth_client
):
    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        vehicle = Vehicle(vehicle_number="=1+1", vehicle_type="4-WHEELER")
        spot = ParkingSpot(
            spot_number="FW-CSV",
            vehicle_type="4-WHEELER",
            distance_from_entry=1,
        )
        db.session.add_all([vehicle, spot])
        db.session.flush()
        db.session.add(
            ParkingSession(
                vehicle=vehicle,
                spot=spot,
                entry_time=now - timedelta(hours=2),
                exit_time=now,
                duration_minutes=120,
                base_fare=Decimal("100.00"),
                tax_amount=Decimal("18.00"),
                final_fare=Decimal("118.00"),
                amount_due=Decimal("118.00"),
                status="COMPLETED",
            )
        )
        db.session.commit()
        entry_date = (now - timedelta(hours=2)).date().isoformat()

    query = f"?vehicle_number=%3D1%2B1&status=COMPLETED&date_from={entry_date}&date_to={entry_date}"
    history = auth_client.get(f"/history{query}")
    assert history.status_code == 200
    assert b"=1+1" in history.data

    report = auth_client.get(f"/history/export{query}")
    assert report.status_code == 200
    assert report.mimetype == "text/csv"
    rows = list(csv.reader(StringIO(report.get_data(as_text=True))))
    assert rows[0][0] == "vehicle_number"
    assert rows[1][0] == "'=1+1"
    assert rows[1][6] == "COMPLETED"

    invalid_history = auth_client.get(
        "/history?vehicle_number=%3D1%2B1&date_from=2026-10-09&date_to=2026-10-08"
    )
    assert b"start date" in invalid_history.data
    assert b"FW-CSV" not in invalid_history.data


def test_history_export_rejects_invalid_date_ranges(auth_client):
    response = auth_client.get(
        "/history/export?date_from=2026-10-09&date_to=2026-10-08"
    )
    assert response.status_code == 400
    assert "start date" in response.get_data(as_text=True)
