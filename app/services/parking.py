from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from flask import current_app

from ..extensions import db
from ..models import Employee, ParkingSession, ParkingSpot, Reservation, Vehicle, utc_now

VEHICLE_TYPES = {"2-WHEELER", "3-WHEELER", "4-WHEELER"}
ACTIVE_RESERVATION_STATUSES = ("PENDING_PAYMENT", "CONFIRMED")
CENT = Decimal("0.01")


def money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def loyalty_tier(visits: int) -> str:
    thresholds = sorted(
        (int(threshold) for threshold in current_app.config["LOYALTY_DISCOUNTS"]),
    )
    tier_names = ("Regular", "Frequent", "Highly Frequent")
    for threshold, name in reversed(list(zip(thresholds, tier_names))):
        if visits >= threshold:
            return name
    return "Occasional" if visits else "New"


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("A valid ISO-8601 date and time is required.") from error
    local_zone = ZoneInfo(current_app.config["PARKING_TIMEZONE"])
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_zone)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_vehicle_number(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Vehicle number must be text.")
    number = "".join(value.upper().split())
    if not 2 <= len(number) <= 20:
        raise ValueError("Vehicle number must contain between 2 and 20 characters.")
    return number


def register_employee(
    employee_code: str, full_name: str, department: str | None = None,
    exemption_percent: int | float | None = None,
    commit: bool = True,
) -> Employee:
    if not isinstance(employee_code, str) or not isinstance(full_name, str):
        raise ValueError("Employee ID and full name must be text.")
    if department is not None and not isinstance(department, str):
        raise ValueError("Department must be text.")
    code = str(employee_code).strip().upper()
    name = str(full_name).strip()
    if not code or not name:
        raise ValueError("Employee ID and full name are required.")
    if len(code) > 50 or len(name) > 100:
        raise ValueError("Employee ID cannot exceed 50 characters and name cannot exceed 100.")
    if department is not None and len(department) > 100:
        raise ValueError("Department cannot exceed 100 characters.")
    if Employee.query.filter_by(employee_code=code).first():
        raise ValueError("Employee ID is already registered.")
    percent = None
    if exemption_percent is not None:
        try:
            percent = Decimal(str(exemption_percent))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("Employee exemption must be a number between 0 and 100.") from error
        if not percent.is_finite() or not 0 <= percent <= 100:
            raise ValueError("Employee exemption must be between 0 and 100 percent.")
    employee = Employee(
        employee_code=code,
        full_name=name,
        department=(department or "").strip() or None,
        exemption_percent=(
            money(percent) if percent is not None else None
        ),
    )
    db.session.add(employee)
    db.session.flush()
    if commit:
        db.session.commit()
    return employee


def register_vehicle(
    vehicle_number: str,
    vehicle_type: str,
    employee_code: str | None = None,
    commit: bool = True,
    owner_id: int | None = None,
) -> Vehicle:
    if not isinstance(vehicle_type, str):
        raise ValueError("Vehicle type must be text.")
    if employee_code is not None and not isinstance(employee_code, str):
        raise ValueError("Employee ID must be text.")
    number = normalize_vehicle_number(vehicle_number)
    kind = str(vehicle_type).strip().upper()
    if kind not in VEHICLE_TYPES:
        raise ValueError("Vehicle type must be 2-WHEELER, 3-WHEELER, or 4-WHEELER.")
    if Vehicle.query.filter_by(vehicle_number=number).first():
        raise ValueError("Vehicle number is already registered.")
    employee = None
    if employee_code:
        employee = Employee.query.filter_by(
            employee_code=str(employee_code).strip().upper(), is_active=True
        ).first()
        if employee is None:
            raise ValueError("No active employee matches that Employee ID.")
    vehicle = Vehicle(
        vehicle_number=number,
        vehicle_type=kind,
        employee=employee,
        owner_id=owner_id,
    )
    db.session.add(vehicle)
    db.session.flush()
    if commit:
        db.session.commit()
    return vehicle


def seed_default_spots() -> int:
    """Add the documented capacity, preserving custom bays and prior seed runs."""
    created = 0
    for vehicle_type, prefix, capacity in (
        ("2-WHEELER", "TW", 200),
        ("3-WHEELER", "THW", 50),
        ("4-WHEELER", "FW", 150),
    ):
        for index in range(1, capacity + 1):
            number = f"{prefix}-{index:03d}"
            if not ParkingSpot.query.filter_by(spot_number=number).first():
                db.session.add(
                    ParkingSpot(
                        spot_number=number,
                        vehicle_type=vehicle_type,
                        distance_from_entry=index,
                    )
                )
                created += 1
    return created


def reservation_spot_ids(vehicle_type: str) -> set[int]:
    """Return the farthest fifth of a category as its reservation pool."""
    spots = ParkingSpot.query.filter_by(vehicle_type=vehicle_type).order_by(
        ParkingSpot.distance_from_entry.desc(), ParkingSpot.id.desc()
    ).all()
    if not spots:
        return set()
    # Keep a usable reservation pool for small/custom categories too.
    reservation_count = max(1, len(spots) // 5)
    return {spot.id for spot in spots[:reservation_count]}


def _reservation_overlap(spot_id: int, starts_at: datetime, ends_at: datetime):
    return Reservation.query.filter(
        Reservation.parking_spot_id == spot_id,
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        Reservation.starts_at < ends_at,
        Reservation.ends_at > starts_at,
    ).first()


def _quote(vehicle: Vehicle, duration_minutes: int) -> dict[str, Decimal]:
    rate = Decimal(str(current_app.config["PARKING_HOURLY_RATES"][vehicle.vehicle_type]))
    billable_hours = max(
        1, int((Decimal(duration_minutes) / Decimal(60)).to_integral_value(rounding=ROUND_CEILING))
    )
    base_fare = money(rate * billable_hours)
    employee_percent = Decimal("0")
    if vehicle.employee and vehicle.employee.is_active:
        configured = vehicle.employee.exemption_percent
        employee_percent = Decimal(
            str(
                configured
                if configured is not None
                else current_app.config["EMPLOYEE_EXEMPTION_PERCENT"]
            )
        )

    visits = ParkingSession.query.filter_by(
        vehicle_id=vehicle.id, status="COMPLETED"
    ).count()
    loyalty_percent = Decimal("0")
    for threshold, percent in sorted(
        current_app.config["LOYALTY_DISCOUNTS"].items(),
        key=lambda item: int(item[0]),
    ):
        if visits >= int(threshold):
            loyalty_percent = Decimal(str(percent))
    employee_discount = money(base_fare * employee_percent / Decimal("100"))
    loyalty_discount = money(
        (base_fare - employee_discount) * loyalty_percent / Decimal("100")
    )
    taxable_amount = max(Decimal("0"), base_fare - employee_discount - loyalty_discount)
    tax_amount = money(
        taxable_amount * Decimal(str(current_app.config["PARKING_TAX_PERCENT"]))
        / Decimal("100")
    )
    return {
        "base_fare": base_fare,
        "employee_discount": employee_discount,
        "loyalty_discount": loyalty_discount,
        "tax_amount": tax_amount,
        "final_fare": money(taxable_amount + tax_amount),
    }


def _refresh_reservation_slots(now: datetime) -> bool:
    currently_reserved = {
        item[0]
        for item in db.session.query(Reservation.parking_spot_id)
        .filter(
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            Reservation.starts_at <= now,
            Reservation.ends_at > now,
        )
        .distinct()
        .all()
    }
    reservation_ids = set().union(
        *(reservation_spot_ids(kind) for kind in VEHICLE_TYPES)
    )
    reserved_spots = ParkingSpot.query.filter(
        ParkingSpot.id.in_(reservation_ids),
        ParkingSpot.status.in_(("AVAILABLE", "RESERVED")),
    ).all()
    changed = False
    for spot in reserved_spots:
        desired_status = "RESERVED" if spot.id in currently_reserved else "AVAILABLE"
        if spot.status != desired_status:
            spot.status = desired_status
            changed = True
    if changed:
        db.session.flush()
    return changed


def check_in(
    vehicle_number: str, reservation_id: int | None = None
) -> ParkingSession:
    number = normalize_vehicle_number(vehicle_number)
    vehicle = Vehicle.query.filter_by(vehicle_number=number).with_for_update().first()
    if vehicle is None:
        raise ValueError("Register the vehicle before checking it in.")
    if ParkingSession.query.filter_by(vehicle_id=vehicle.id, status="ACTIVE").first():
        raise ValueError("This vehicle already has an active parking session.")

    now = utc_now()
    _refresh_reservation_slots(now)
    reservation = None
    if reservation_id is not None:
        try:
            reservation_id = int(reservation_id)
        except (TypeError, ValueError) as error:
            raise ValueError("Reservation ID must be a positive integer.") from error
        if reservation_id < 1:
            raise ValueError("Reservation ID must be a positive integer.")
        reservation = db.session.get(Reservation, reservation_id)
        if (
            reservation is None
            or reservation.vehicle_id != vehicle.id
            or reservation.status != "CONFIRMED"
            or reservation.payment_status != "PAID"
        ):
            raise ValueError("A paid, confirmed reservation for this vehicle is required.")
        if now < reservation.starts_at or now >= reservation.ends_at:
            raise ValueError("Check-in is outside the reservation time window.")
        spot = db.session.get(ParkingSpot, reservation.parking_spot_id)
        if spot is not None:
            db.session.refresh(spot, with_for_update=True)
        if spot is None or spot.status not in ("AVAILABLE", "RESERVED"):
            raise ValueError("The reserved parking spot is not available.")
    else:
        reservation_ids = reservation_spot_ids(vehicle.vehicle_type)
        candidates = (
            ParkingSpot.query.filter_by(
                vehicle_type=vehicle.vehicle_type, status="AVAILABLE"
            )
            .order_by(ParkingSpot.distance_from_entry, ParkingSpot.id)
            .with_for_update()
            .all()
        )
        available = [
            candidate for candidate in candidates
            if _reservation_overlap(candidate.id, now, datetime.max) is None
        ]
        spot = next(
            (candidate for candidate in available if candidate.id not in reservation_ids),
            None,
        )
        if spot is None:
            spot = next(
                (candidate for candidate in available if candidate.id in reservation_ids),
                None,
            )
        if spot is None:
            raise ValueError("No compatible parking spot is currently available.")

    spot.status = "OCCUPIED"
    session = ParkingSession(
        vehicle=vehicle,
        spot=spot,
        reservation=reservation,
        entry_time=now,
        status="ACTIVE",
        prepaid_amount=reservation.estimated_fare if reservation else 0,
    )
    if reservation:
        reservation.status = "CHECKED_IN"
    db.session.add(session)
    db.session.commit()
    return session


def check_out(vehicle_number: str) -> ParkingSession:
    number = normalize_vehicle_number(vehicle_number)
    vehicle = Vehicle.query.filter_by(vehicle_number=number).first()
    if vehicle is None:
        raise ValueError("Vehicle is not registered.")
    session = ParkingSession.query.filter_by(
        vehicle_id=vehicle.id, status="ACTIVE"
    ).with_for_update().first()
    if session is None:
        raise ValueError("This vehicle has no active parking session.")
    now = utc_now()
    duration_seconds = max(60, int((now - session.entry_time).total_seconds()))
    session.duration_minutes = max(1, (duration_seconds + 59) // 60)
    session.exit_time = now
    session.status = "COMPLETED"
    for field, amount in _quote(vehicle, session.duration_minutes).items():
        setattr(session, field, amount)
    session.amount_due = max(
        Decimal("0"), session.final_fare - Decimal(str(session.prepaid_amount))
    )
    if session.reservation:
        overstay_seconds = max(
            0, int((now - session.reservation.ends_at).total_seconds())
        )
        session.overstay_minutes = (overstay_seconds + 59) // 60
    session.spot.status = "AVAILABLE"
    if session.reservation:
        session.reservation.status = "COMPLETED"
    _refresh_reservation_slots(now)
    db.session.commit()
    return session


def create_reservation(
    vehicle_number: str, starts_at: str | datetime, ends_at: str | datetime
) -> Reservation:
    number = normalize_vehicle_number(vehicle_number)
    vehicle = Vehicle.query.filter_by(vehicle_number=number).first()
    if vehicle is None:
        raise ValueError("Register the vehicle before making a reservation.")
    start, end = parse_datetime(starts_at), parse_datetime(ends_at)
    now = utc_now()
    if start <= now:
        raise ValueError("Reservation start time must be in the future.")
    if end <= start:
        raise ValueError("Reservation end time must be after its start time.")
    _refresh_reservation_slots(now)
    duration_minutes = max(1, int((end - start).total_seconds() // 60))
    reservation_ids = reservation_spot_ids(vehicle.vehicle_type)
    candidates = (
        ParkingSpot.query.filter_by(vehicle_type=vehicle.vehicle_type, status="AVAILABLE")
        .order_by(ParkingSpot.distance_from_entry, ParkingSpot.id)
        .with_for_update()
        .all()
    )
    spot = next(
        (
            candidate
            for candidate in candidates
            if candidate.id in reservation_ids
            and _reservation_overlap(candidate.id, start, end) is None
            and not ParkingSession.query.filter_by(
                parking_spot_id=candidate.id, status="ACTIVE"
            ).first()
        ),
        None,
    )
    if spot is None:
        raise ValueError("No compatible spot is available for the requested time.")
    quote = _quote(vehicle, duration_minutes)
    reservation = Reservation(
        vehicle=vehicle,
        spot=spot,
        starts_at=start,
        ends_at=end,
        estimated_fare=quote["final_fare"],
        payment_status="PENDING",
        status="PENDING_PAYMENT",
    )
    db.session.add(reservation)
    db.session.commit()
    return reservation


def confirm_reservation_payment(reservation_id: int) -> Reservation:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None:
        raise ValueError("Reservation was not found.")
    if reservation.status != "PENDING_PAYMENT":
        raise ValueError("Only unpaid pending reservations can be confirmed.")
    reservation.payment_status = "PAID"
    reservation.status = "CONFIRMED"
    db.session.commit()
    return reservation


def cancel_reservation(reservation_id: int) -> Reservation:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None:
        raise ValueError("Reservation was not found.")
    if reservation.status not in ("PENDING_PAYMENT", "CONFIRMED"):
        raise ValueError("This reservation can no longer be cancelled.")
    reservation.status = "CANCELLED"
    _refresh_reservation_slots(utc_now())
    db.session.commit()
    return reservation


def parking_analytics() -> dict:
    now = utc_now()
    if _refresh_reservation_slots(now):
        db.session.commit()
    spots = ParkingSpot.query.all()
    counts = {status: 0 for status in (
        "AVAILABLE", "OCCUPIED", "RESERVED", "MAINTENANCE", "BLOCKED"
    )}
    by_type = {vehicle_type: {"total": 0, "occupied": 0} for vehicle_type in VEHICLE_TYPES}
    for spot in spots:
        counts[spot.status] = counts.get(spot.status, 0) + 1
        by_type.setdefault(spot.vehicle_type, {"total": 0, "occupied": 0})
        by_type[spot.vehicle_type]["total"] += 1
        if spot.status == "OCCUPIED":
            by_type[spot.vehicle_type]["occupied"] += 1

    completed = ParkingSession.query.filter_by(status="COMPLETED").all()
    active = ParkingSession.query.filter_by(status="ACTIVE").order_by(
        ParkingSession.entry_time.desc()
    ).all()
    revenue = money(sum((Decimal(str(item.final_fare)) for item in completed), Decimal("0")))
    durations = [item.duration_minutes for item in completed if item.duration_minutes]
    hour_counts: dict[str, int] = {}
    day_counts: dict[str, int] = {}
    local_zone = ZoneInfo(current_app.config["PARKING_TIMEZONE"])
    for item in completed:
        local_entry = item.entry_time.replace(tzinfo=timezone.utc).astimezone(local_zone)
        hour = str(local_entry.hour).zfill(2)
        day = local_entry.strftime("%A")
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
        day_counts[day] = day_counts.get(day, 0) + 1
    frequent = (
        db.session.query(Vehicle.vehicle_number, db.func.count(ParkingSession.id).label("visits"))
        .join(ParkingSession)
        .filter(ParkingSession.status == "COMPLETED")
        .group_by(Vehicle.id, Vehicle.vehicle_number)
        .order_by(db.func.count(ParkingSession.id).desc())
        .limit(5)
        .all()
    )
    total = len(spots)
    utilization_window = timedelta(days=30)
    utilization_start = now - utilization_window
    occupied_seconds_by_spot: dict[int, float] = {}
    visits_by_spot: dict[int, int] = {}
    utilization_sessions = ParkingSession.query.filter(
        ParkingSession.status.in_(("ACTIVE", "COMPLETED")),
        ParkingSession.entry_time < now,
        db.or_(
            ParkingSession.exit_time.is_(None),
            ParkingSession.exit_time > utilization_start,
        ),
    ).all()
    for item in utilization_sessions:
        occupied_start = max(item.entry_time, utilization_start)
        occupied_end = min(item.exit_time or now, now)
        occupied_seconds_by_spot[item.parking_spot_id] = (
            occupied_seconds_by_spot.get(item.parking_spot_id, 0)
            + max(0, (occupied_end - occupied_start).total_seconds())
        )
        visits_by_spot[item.parking_spot_id] = (
            visits_by_spot.get(item.parking_spot_id, 0) + 1
        )

    local_today = now.replace(tzinfo=timezone.utc).astimezone(local_zone).date()
    demand_start = datetime.combine(local_today, time.min, tzinfo=local_zone)
    demand_end = datetime.combine(
        local_today + timedelta(days=7), time.min, tzinfo=local_zone
    )
    demand_start_utc = demand_start.astimezone(timezone.utc).replace(tzinfo=None)
    demand_end_utc = demand_end.astimezone(timezone.utc).replace(tzinfo=None)
    demand_counts = {local_today + timedelta(days=i): 0 for i in range(7)}
    upcoming_reservations = Reservation.query.filter(
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        Reservation.starts_at >= demand_start_utc,
        Reservation.starts_at < demand_end_utc,
    ).all()
    for reservation in upcoming_reservations:
        local_start = reservation.starts_at.replace(tzinfo=timezone.utc).astimezone(local_zone)
        demand_counts[local_start.date()] += 1

    return {
        "total_slots": total,
        "occupied_slots": counts["OCCUPIED"],
        "available_slots": counts["AVAILABLE"],
        "occupancy_percent": round(counts["OCCUPIED"] * 100 / total, 2) if total else 0,
        "slot_status_counts": counts,
        "vehicle_type_distribution": by_type,
        "active_sessions": active,
        "completed_sessions": len(completed),
        "revenue": revenue,
        "average_duration_minutes": (
            round(sum(durations) / len(durations), 2) if durations else 0
        ),
        "peak_hours": sorted(hour_counts.items(), key=lambda item: (-item[1], item[0]))[:5],
        "peak_days": sorted(day_counts.items(), key=lambda item: (-item[1], item[0]))[:7],
        "frequent_vehicles": [
            {
                "vehicle_number": number,
                "visits": visits,
                "loyalty_tier": loyalty_tier(visits),
            }
            for number, visits in frequent
        ],
        "employee_sessions": sum(
            1 for item in completed if item.vehicle.employee_id is not None
        ),
        "non_employee_sessions": sum(
            1 for item in completed if item.vehicle.employee_id is None
        ),
        "reservation_count": Reservation.query.count(),
        "reservation_demand": [
            {
                "date": day.isoformat(),
                "day": day.strftime("%a"),
                "count": count,
            }
            for day, count in demand_counts.items()
        ],
        "slot_utilization": [
            {
                "spot_id": spot.id,
                "spot_number": spot.spot_number,
                "vehicle_type": spot.vehicle_type,
                "distance_from_entry": spot.distance_from_entry,
                "status": spot.status,
                "visits_30d": visits_by_spot.get(spot.id, 0),
                "utilization_percent": min(
                    100,
                    round(
                        occupied_seconds_by_spot.get(spot.id, 0)
                        / utilization_window.total_seconds()
                        * 100,
                        2,
                    ),
                ),
            }
            for spot in sorted(
                spots,
                key=lambda item: (
                    item.vehicle_type,
                    item.distance_from_entry,
                    item.id,
                ),
            )
        ],
    }
