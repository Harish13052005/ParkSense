from flask import redirect, render_template, url_for
from flask_login import current_user

from .blueprints import main_bp
from ..models import ParkingSpot, Reservation, Vehicle
from ..services.parking import parking_analytics


@main_bp.route("/")
def home():
    if not current_user.is_authenticated:
        return render_template("landing.html")
    if not current_user.is_admin:
        return redirect(url_for("main.account"))
    stats = parking_analytics()
    reservations = Reservation.query.order_by(Reservation.starts_at).limit(10).all()
    vehicles = Vehicle.query.order_by(Vehicle.vehicle_number).all()
    utilization = {
        item["spot_id"]: item["utilization_percent"]
        for item in stats["slot_utilization"]
    }
    spot_map = {}
    for spot in ParkingSpot.query.order_by(
        ParkingSpot.vehicle_type, ParkingSpot.distance_from_entry, ParkingSpot.id
    ).all():
        spot_map.setdefault(spot.vehicle_type, []).append(
            {
                "spot": spot,
                "utilization_percent": utilization.get(spot.id, 0),
            }
        )
    return render_template(
        "home.html",
        stats=stats,
        reservations=reservations,
        vehicles=vehicles,
        spot_map=spot_map,
    )
