import csv
from datetime import date, timedelta
from io import StringIO

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from .blueprints import main_bp
from .common import admin_required
from ..extensions import db
from ..models import Employee, ParkingSession, ParkingSpot, Vehicle
from ..services.parking import (
    cancel_reservation, check_in, check_out, confirm_reservation_payment,
    create_reservation, normalize_vehicle_number, parse_datetime,
    register_employee, register_vehicle,
)


@main_bp.route("/spots")
@admin_required
def list_spots():
    spots = ParkingSpot.query.order_by(ParkingSpot.distance_from_entry, ParkingSpot.id).all()
    return render_template("spots.html", spots=spots)

@main_bp.route("/operations/vehicle", methods=["POST"])
@admin_required
def add_vehicle():
    try:
        employee_code = request.form.get("employee_code", "").strip() or None
        if request.form.get("employee_name", "").strip():
            employee = register_employee(
                employee_code or "",
                request.form["employee_name"],
                request.form.get("department"),
                request.form.get("exemption_percent") or None,
                commit=False,
            )
            employee_code = employee.employee_code
        vehicle = register_vehicle(
            request.form.get("vehicle_number", ""),
            request.form.get("vehicle_type", ""),
            employee_code,
            commit=False,
        )
        db.session.commit()
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        message = (
            str(error)
            if isinstance(error, ValueError)
            else "A duplicate employee ID or vehicle number already exists."
        )
        flash(message, "danger")
    else:
        flash(f"Vehicle {vehicle.vehicle_number} registered.", "success")
    return redirect(url_for("main.home"))

@main_bp.route("/operations/entry", methods=["POST"])
@admin_required
def vehicle_entry():
    try:
        session = check_in(
            request.form.get("vehicle_number", ""),
            int(request.form["reservation_id"])
            if request.form.get("reservation_id")
            else None,
        )
    except (TypeError, ValueError) as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash(
            f"{session.vehicle.vehicle_number} checked in to {session.spot.spot_number}.",
            "success",
        )
    return redirect(url_for("main.home"))

@main_bp.route("/operations/exit", methods=["POST"])
@admin_required
def vehicle_exit():
    try:
        session = check_out(request.form.get("vehicle_number", ""))
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash(
            f"Checkout complete. Duration: {session.duration_minutes} minutes; "
            f"amount due: {session.final_fare}.",
            "success",
        )
    return redirect(url_for("main.home"))

@main_bp.route("/operations/reservation", methods=["POST"])
@admin_required
def add_reservation():
    try:
        reservation = create_reservation(
            request.form.get("vehicle_number", ""),
            request.form.get("starts_at", ""),
            request.form.get("ends_at", ""),
        )
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash(
            f"Reservation #{reservation.id} created. Estimated fare: "
            f"{reservation.estimated_fare}. Confirm advance payment to finalize.",
            "success",
        )
    return redirect(url_for("main.home"))

@main_bp.route("/operations/reservation/<int:reservation_id>/payment", methods=["POST"])
@admin_required
def reservation_payment(reservation_id: int):
    try:
        confirm_reservation_payment(reservation_id)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash(
            "Demo advance payment recorded; reservation is confirmed.",
            "success",
        )
    return redirect(url_for("main.home"))

@main_bp.route("/operations/reservation/<int:reservation_id>/cancel", methods=["POST"])
@admin_required
def reservation_cancel(reservation_id: int):
    try:
        cancel_reservation(reservation_id)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash("Reservation cancelled.", "info")
    return redirect(url_for("main.home"))

@main_bp.route("/admin/employees", methods=["GET", "POST"])
@admin_required
def employees():
    if request.method == "POST":
        try:
            employee = register_employee(
                request.form.get("employee_code", ""),
                request.form.get("full_name", ""),
                request.form.get("department"),
                request.form.get("exemption_percent") or None,
            )
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            message = (
                str(error)
                if isinstance(error, ValueError)
                else "That employee ID is already registered."
            )
            flash(message, "danger")
        else:
            flash(f"Employee {employee.employee_code} registered.", "success")
        return redirect(url_for("main.employees"))
    employee_list = Employee.query.order_by(Employee.employee_code).all()
    return render_template("employees.html", employees=employee_list)

@main_bp.route("/admin/employees/<int:employee_id>/status", methods=["POST"])
@admin_required
def employee_status(employee_id: int):
    employee = db.session.get(Employee, employee_id)
    if employee is None:
        flash("Employee was not found.", "danger")
        return redirect(url_for("main.employees"))
    employee.is_active = request.form.get("is_active") == "true"
    db.session.commit()
    state = "activated" if employee.is_active else "deactivated"
    flash(f"Employee {employee.employee_code} {state}.", "success")
    return redirect(url_for("main.employees"))

@main_bp.route("/history")
@admin_required
def history():
    filters = {
        "vehicle_number": request.args.get("vehicle_number", "").strip(),
        "status": request.args.get("status", "").strip().upper(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }
    try:
        query = _filtered_history_query(filters)
    except ValueError as error:
        flash(str(error), "danger")
        sessions = []
    else:
        sessions = query.limit(200).all()
    return render_template("history.html", sessions=sessions, filters=filters)

def _filtered_history_query(filters):
    query = ParkingSession.query.order_by(ParkingSession.entry_time.desc())
    vehicle_number = filters["vehicle_number"]
    if vehicle_number:
        query = query.join(Vehicle).filter(
            Vehicle.vehicle_number == normalize_vehicle_number(vehicle_number)
        )

    status = filters["status"]
    if status and status != "ALL":
        if status not in ("ACTIVE", "COMPLETED", "CANCELLED"):
            raise ValueError("Choose a valid visit status.")
        query = query.filter(ParkingSession.status == status)

    date_from = filters["date_from"]
    date_to = filters["date_to"]
    try:
        first_date = date.fromisoformat(date_from) if date_from else None
        last_date = date.fromisoformat(date_to) if date_to else None
        if (
            (first_date and first_date.isoformat() != date_from)
            or (last_date and last_date.isoformat() != date_to)
        ):
            raise ValueError
    except ValueError as error:
        raise ValueError("Dates must use the YYYY-MM-DD format.") from error
    if first_date and last_date and first_date > last_date:
        raise ValueError("The start date must not be after the end date.")
    if first_date:
        query = query.filter(
            ParkingSession.entry_time
            >= parse_datetime(f"{first_date.isoformat()}T00:00:00")
        )
    if last_date:
        day_after = last_date + timedelta(days=1)
        query = query.filter(
            ParkingSession.entry_time
            < parse_datetime(f"{day_after.isoformat()}T00:00:00")
        )
    return query

@main_bp.route("/history/export")
@admin_required
def export_history():
    filters = {
        "vehicle_number": request.args.get("vehicle_number", "").strip(),
        "status": request.args.get("status", "").strip().upper(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }
    try:
        sessions = _filtered_history_query(filters).limit(10000).all()
    except ValueError as error:
        return Response(str(error), status=400, mimetype="text/plain")

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "vehicle_number",
            "vehicle_type",
            "parking_bay",
            "entry_time_utc",
            "exit_time_utc",
            "duration_minutes",
            "status",
            "base_fare",
            "employee_discount",
            "loyalty_discount",
            "tax_amount",
            "prepaid_amount",
            "final_fare",
            "amount_due",
            "overstay_minutes",
        ]
    )
    for session in sessions:
        vehicle_number = session.vehicle.vehicle_number
        spot_number = session.spot.spot_number
        if vehicle_number.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
            vehicle_number = "'" + vehicle_number
        if spot_number.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
            spot_number = "'" + spot_number
        writer.writerow(
            [
                vehicle_number,
                session.vehicle.vehicle_type,
                spot_number,
                session.entry_time.isoformat() + "Z",
                session.exit_time.isoformat() + "Z" if session.exit_time else "",
                session.duration_minutes if session.duration_minutes is not None else "",
                session.status,
                session.base_fare,
                session.employee_discount,
                session.loyalty_discount,
                session.tax_amount,
                session.prepaid_amount,
                session.final_fare,
                session.amount_due,
                session.overstay_minutes,
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=parksense-visits.csv"},
    )
