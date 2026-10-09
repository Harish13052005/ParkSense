from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import ParkingSession, ParkingSpot, Reservation, Vehicle
from ..services.parking import (
    cancel_reservation,
    check_in,
    check_out,
    confirm_reservation_payment,
    create_reservation,
    loyalty_tier,
    parking_analytics,
    register_employee,
    register_vehicle,
)
from .jwt_utils import jwt_required

workflow_bp = Blueprint("parking_workflow_api", __name__, url_prefix="/api")


def _error_response(error: ValueError, status: int = 400):
    db.session.rollback()
    return jsonify({"error": str(error)}), status


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "A JSON object is required"}), 400)
    return data, None


def _session_json(item: ParkingSession) -> dict:
    return {
        "id": item.id,
        "vehicle_number": item.vehicle.vehicle_number,
        "vehicle_type": item.vehicle.vehicle_type,
        "spot_number": item.spot.spot_number,
        "entry_time": item.entry_time.isoformat() + "Z",
        "exit_time": item.exit_time.isoformat() + "Z" if item.exit_time else None,
        "duration_minutes": item.duration_minutes,
        "status": item.status,
        "base_fare": str(item.base_fare),
        "employee_discount": str(item.employee_discount),
        "loyalty_discount": str(item.loyalty_discount),
        "tax_amount": str(item.tax_amount),
        "final_fare": str(item.final_fare),
        "prepaid_amount": str(item.prepaid_amount),
        "amount_due": str(item.amount_due),
        "overstay_minutes": item.overstay_minutes,
    }


def _reservation_json(item: Reservation) -> dict:
    return {
        "id": item.id,
        "vehicle_number": item.vehicle.vehicle_number,
        "spot_number": item.spot.spot_number,
        "starts_at": item.starts_at.isoformat() + "Z",
        "ends_at": item.ends_at.isoformat() + "Z",
        "estimated_fare": str(item.estimated_fare),
        "payment_status": item.payment_status,
        "status": item.status,
    }


@workflow_bp.post("/employees")
@jwt_required
def create_employee():
    data, error = _json_body()
    if error:
        return error
    try:
        employee = register_employee(
            data.get("employee_code", ""),
            data.get("full_name", ""),
            data.get("department"),
            data.get("exemption_percent"),
        )
    except ValueError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Employee ID is already registered."}), 409
    return jsonify(
        {
            "id": employee.id,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "department": employee.department,
            "exemption_percent": (
                str(employee.exemption_percent)
                if employee.exemption_percent is not None
                else None
            ),
        }
    ), 201


@workflow_bp.post("/vehicles")
@jwt_required
def create_vehicle():
    data, error = _json_body()
    if error:
        return error
    try:
        vehicle = register_vehicle(
            data.get("vehicle_number", ""),
            data.get("vehicle_type", ""),
            data.get("employee_code"),
        )
    except ValueError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {"error": "Vehicle number is already registered or employee ID is invalid."}
        ), 409
    return jsonify(
        {
            "id": vehicle.id,
            "vehicle_number": vehicle.vehicle_number,
            "vehicle_type": vehicle.vehicle_type,
            "employee_code": (
                vehicle.employee.employee_code if vehicle.employee else None
            ),
        }
    ), 201


@workflow_bp.get("/vehicles")
@jwt_required
def list_vehicles():
    visits_by_vehicle = dict(
        db.session.query(
            ParkingSession.vehicle_id, func.count(ParkingSession.id)
        )
        .filter(ParkingSession.status == "COMPLETED")
        .group_by(ParkingSession.vehicle_id)
        .all()
    )
    vehicles = (
        Vehicle.query.options(selectinload(Vehicle.employee))
        .order_by(Vehicle.vehicle_number)
        .all()
    )
    items = []
    for vehicle in vehicles:
        visits = visits_by_vehicle.get(vehicle.id, 0)
        items.append(
            {
                "id": vehicle.id,
                "vehicle_number": vehicle.vehicle_number,
                "vehicle_type": vehicle.vehicle_type,
                "employee_code": (
                    vehicle.employee.employee_code if vehicle.employee else None
                ),
                "visits": visits,
                "loyalty_tier": loyalty_tier(visits),
            }
        )
    return jsonify(items)


@workflow_bp.post("/entry")
@jwt_required
def vehicle_entry():
    data, error = _json_body()
    if error:
        return error
    try:
        session = check_in(data.get("vehicle_number", ""), data.get("reservation_id"))
    except (TypeError, ValueError) as error:
        return _error_response(ValueError(str(error)))
    return jsonify(_session_json(session)), 201


@workflow_bp.post("/exit")
@jwt_required
def vehicle_exit():
    data, error = _json_body()
    if error:
        return error
    try:
        session = check_out(data.get("vehicle_number", ""))
    except ValueError as error:
        return _error_response(error)
    return jsonify(_session_json(session))


@workflow_bp.route("/reservations", methods=["GET", "POST"])
@jwt_required
def reservations():
    if request.method == "GET":
        items = Reservation.query.order_by(Reservation.starts_at.desc()).limit(200).all()
        return jsonify([_reservation_json(item) for item in items])
    data, error = _json_body()
    if error:
        return error
    try:
        item = create_reservation(
            data.get("vehicle_number", ""),
            data.get("starts_at", ""),
            data.get("ends_at", ""),
        )
    except (TypeError, ValueError) as error:
        return _error_response(ValueError(str(error)))
    return jsonify(_reservation_json(item)), 201


@workflow_bp.post("/reservations/<int:reservation_id>/confirm-payment")
@jwt_required
def reservation_payment(reservation_id: int):
    try:
        item = confirm_reservation_payment(reservation_id)
    except ValueError as error:
        return _error_response(error)
    return jsonify(_reservation_json(item))


@workflow_bp.post("/reservations/<int:reservation_id>/cancel")
@jwt_required
def reservation_cancel(reservation_id: int):
    try:
        item = cancel_reservation(reservation_id)
    except ValueError as error:
        return _error_response(error)
    return jsonify(_reservation_json(item))


@workflow_bp.get("/history")
@jwt_required
def parking_history():
    query = ParkingSession.query.order_by(ParkingSession.entry_time.desc())
    vehicle_number = request.args.get("vehicle_number")
    if vehicle_number:
        query = query.join(Vehicle).filter(
            Vehicle.vehicle_number == vehicle_number.strip().upper()
        )
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    except ValueError:
        return jsonify({"error": "limit must be a number between 1 and 500"}), 400
    return jsonify([_session_json(item) for item in query.limit(limit).all()])


@workflow_bp.get("/analytics")
@jwt_required
def analytics():
    result = parking_analytics()
    result["revenue"] = str(result["revenue"])
    result["active_sessions"] = [_session_json(item) for item in result["active_sessions"]]
    result["peak_hours"] = [
        {"hour": hour, "visits": visits} for hour, visits in result["peak_hours"]
    ]
    result["peak_days"] = [
        {"day": day, "visits": visits} for day, visits in result["peak_days"]
    ]
    return jsonify(result)


@workflow_bp.patch("/spots/<int:spot_id>/status")
@jwt_required
def update_spot_status(spot_id: int):
    data, error = _json_body()
    if error:
        return error
    status = data.get("status")
    if status not in ("AVAILABLE", "MAINTENANCE", "BLOCKED"):
        return jsonify({"error": "Status must be AVAILABLE, MAINTENANCE, or BLOCKED"}), 400
    spot = db.session.get(ParkingSpot, spot_id)
    if spot is None:
        return jsonify({"error": "Spot not found"}), 404
    if spot.status in ("OCCUPIED", "RESERVED"):
        return jsonify({"error": "Occupied or reserved spots cannot be taken out of service"}), 409
    spot.status = status
    db.session.commit()
    return jsonify(
        {
            "id": spot.id,
            "spot_number": spot.spot_number,
            "vehicle_type": spot.vehicle_type,
            "distance_from_entry": spot.distance_from_entry,
            "status": spot.status,
        }
    )
