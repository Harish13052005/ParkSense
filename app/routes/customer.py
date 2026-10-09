from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from .blueprints import main_bp
from .common import customer_required
from ..extensions import db
from ..models import ParkingSession, Reservation, Vehicle
from ..services.parking import (
    cancel_reservation, confirm_reservation_payment, create_reservation,
    normalize_vehicle_number, register_vehicle,
)


@main_bp.route("/account")
@customer_required
def account():
    vehicles = Vehicle.query.filter_by(owner_id=current_user.id).order_by(
        Vehicle.vehicle_number
    ).all()
    vehicle_ids = [vehicle.id for vehicle in vehicles]
    reservations = (
        Reservation.query.filter(Reservation.vehicle_id.in_(vehicle_ids))
        .order_by(Reservation.starts_at.desc())
        .limit(100)
        .all()
        if vehicle_ids
        else []
    )
    sessions = (
        ParkingSession.query.filter(ParkingSession.vehicle_id.in_(vehicle_ids))
        .order_by(ParkingSession.entry_time.desc())
        .limit(100)
        .all()
        if vehicle_ids
        else []
    )
    return render_template(
        "account.html",
        vehicles=vehicles,
        reservations=reservations,
        sessions=sessions,
    )

@main_bp.route("/account/vehicles/add", methods=["POST"])
@customer_required
def account_add_vehicle():
    try:
        vehicle = register_vehicle(
            request.form.get("vehicle_number", ""),
            request.form.get("vehicle_type", ""),
            owner_id=current_user.id,
        )
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        message = (
            str(error)
            if isinstance(error, ValueError)
            else "That vehicle registration is already in use."
        )
        flash(message, "danger")
    else:
        flash(f"Vehicle {vehicle.vehicle_number} added to your account.", "success")
    return redirect(url_for("main.account"))

@main_bp.route("/account/vehicles/<int:vehicle_id>/remove", methods=["POST"])
@customer_required
def account_remove_vehicle(vehicle_id: int):
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id, owner_id=current_user.id
    ).first()
    if vehicle is None:
        flash("Vehicle was not found in your account.", "danger")
    elif vehicle.sessions or Reservation.query.filter_by(vehicle_id=vehicle.id).first():
        flash("A vehicle with parking history or reservations cannot be removed.", "warning")
    else:
        db.session.delete(vehicle)
        db.session.commit()
        flash(f"Vehicle {vehicle.vehicle_number} removed.", "success")
    return redirect(url_for("main.account"))

@main_bp.route("/account/reservations", methods=["POST"])
@customer_required
def account_add_reservation():
    try:
        number = normalize_vehicle_number(request.form.get("vehicle_number", ""))
        vehicle = Vehicle.query.filter_by(
            vehicle_number=number, owner_id=current_user.id
        ).first()
        if vehicle is None:
            raise ValueError("Choose a vehicle registered to your account.")
        reservation = create_reservation(
            number,
            request.form.get("starts_at", ""),
            request.form.get("ends_at", ""),
        )
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash(
            f"Reservation #{reservation.id} created for {number}. "
            f"Estimated fare: {reservation.estimated_fare}.",
            "success",
        )
    return redirect(url_for("main.account"))

@main_bp.route(
    "/account/reservations/<int:reservation_id>/<action>", methods=["POST"]
)
@customer_required
def account_reservation_action(reservation_id: int, action: str):
    reservation = (
        Reservation.query.join(Vehicle)
        .filter(
            Reservation.id == reservation_id,
            Vehicle.owner_id == current_user.id,
        )
        .first()
    )
    if reservation is None:
        flash("Reservation was not found in your account.", "danger")
    elif action not in ("payment", "cancel"):
        flash("Unknown reservation action.", "danger")
    else:
        try:
            if action == "payment":
                confirm_reservation_payment(reservation_id)
                flash("Demo advance payment recorded; no real payment was processed.", "success")
            else:
                cancel_reservation(reservation_id)
                flash("Reservation cancelled.", "info")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    return redirect(url_for("main.account"))
