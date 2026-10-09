from flask import request
from flask_restx import Resource, abort, fields

from ..extensions import db
from ..models import ParkingSpot
from ..services.parking import VEHICLE_TYPES, reservation_spot_ids
from . import api
from .jwt_utils import jwt_required

spot_model = api.model(
    "ParkingSpot",
    {
        "id": fields.Integer(readonly=True),
        "spot_number": fields.String(required=True),
        "vehicle_type": fields.String,
        "distance_from_entry": fields.Integer,
        "status": fields.String,
        "is_occupied": fields.Boolean,
        "reservation_only": fields.Boolean,
    },
)
spot_update_model = api.model(
    "ParkingSpotUpdate",
    {
        "spot_number": fields.String,
        "vehicle_type": fields.String,
        "distance_from_entry": fields.Integer,
        "status": fields.String,
        "is_occupied": fields.Boolean,
    },
)


def get_spot_or_404(spot_id: int) -> ParkingSpot:
    spot = db.session.get(ParkingSpot, spot_id)
    if spot is None:
        abort(404, "Spot not found")
    return spot


@api.route("/spots")
class SpotList(Resource):
    @jwt_required
    @api.marshal_list_with(spot_model)
    def get(self):
        spots = ParkingSpot.query.order_by(ParkingSpot.id).all()
        reservation_ids = set().union(
            *(reservation_spot_ids(kind) for kind in VEHICLE_TYPES)
        )
        for spot in spots:
            spot.reservation_only = spot.id in reservation_ids
        return spots

    @jwt_required
    @api.expect(spot_model, validate=True)
    @api.marshal_with(spot_model, code=201)
    def post(self):
        data = request.get_json() or {}
        spot_number = str(data.get("spot_number", "")).strip().upper()
        vehicle_type = data.get("vehicle_type", "4-WHEELER")
        distance = data.get("distance_from_entry", 0)
        if not spot_number or len(spot_number) > 20:
            abort(400, "spot_number must contain between 1 and 20 characters")
        if vehicle_type not in VEHICLE_TYPES:
            abort(400, "Invalid vehicle_type")
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
            abort(400, "distance_from_entry must be a non-negative integer")
        if ParkingSpot.query.filter_by(spot_number=spot_number).first():
            abort(400, "spot_number already exists")
        spot = ParkingSpot(
            spot_number=spot_number,
            vehicle_type=vehicle_type,
            distance_from_entry=distance,
            status="OCCUPIED" if data.get("is_occupied", False) else "AVAILABLE",
        )
        db.session.add(spot)
        db.session.commit()
        spot.reservation_only = spot.id in reservation_spot_ids(vehicle_type)
        return spot, 201


@api.route("/spots/<int:spot_id>")
@api.response(404, "Spot not found")
class SpotDetail(Resource):
    @jwt_required
    @api.marshal_with(spot_model)
    def get(self, spot_id):
        return get_spot_or_404(spot_id)

    @jwt_required
    @api.expect(spot_update_model, validate=True)
    @api.marshal_with(spot_model)
    def put(self, spot_id):
        spot = get_spot_or_404(spot_id)
        data = request.get_json() or {}
        if "spot_number" in data:
            spot_number = str(data["spot_number"]).strip().upper()
            duplicate = ParkingSpot.query.filter(
                ParkingSpot.spot_number == spot_number,
                ParkingSpot.id != spot.id,
            ).first()
            if not spot_number or duplicate:
                abort(400, "spot_number must be unique and non-empty")
            if len(spot_number) > 20:
                abort(400, "spot_number cannot exceed 20 characters")
            spot.spot_number = spot_number
        if "vehicle_type" in data:
            if data["vehicle_type"] not in VEHICLE_TYPES:
                abort(400, "Invalid vehicle_type")
            spot.vehicle_type = data["vehicle_type"]
        if "distance_from_entry" in data:
            distance = data["distance_from_entry"]
            if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
                abort(400, "distance_from_entry must be a non-negative integer")
            spot.distance_from_entry = data["distance_from_entry"]
        if "status" in data:
            if data["status"] not in (
                "AVAILABLE", "MAINTENANCE", "BLOCKED", "RESERVED", "OCCUPIED"
            ):
                abort(400, "Invalid parking spot status")
            if spot.status in ("OCCUPIED", "RESERVED") and data["status"] in (
                "AVAILABLE", "MAINTENANCE", "BLOCKED"
            ):
                abort(409, "An occupied or reserved spot cannot be taken out of service")
            if data["status"] in ("OCCUPIED", "RESERVED") and data["status"] != spot.status:
                abort(409, "Occupancy and reservations must be changed through the parking workflow")
            spot.status = data["status"]
        elif "is_occupied" in data:
            if spot.status not in ("AVAILABLE", "OCCUPIED"):
                abort(409, "Reserved or out-of-service spots cannot be toggled")
            spot.is_occupied = bool(data["is_occupied"])
        db.session.commit()
        return spot

    @jwt_required
    @api.response(204, "Spot deleted")
    def delete(self, spot_id):
        spot = get_spot_or_404(spot_id)
        if spot.status != "AVAILABLE" or spot.sessions:
            abort(409, "Only an unused available spot can be deleted")
        db.session.delete(spot)
        db.session.commit()
        return "", 204
