from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import event, inspect
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """An administrator or customer account."""

    __tablename__ = "user"
    __table_args__ = (
        db.CheckConstraint("role IN ('ADMIN', 'CUSTOMER')", name="ck_user_role"),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, unique=True, index=True)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="CUSTOMER", index=True)
    vehicles = db.relationship("Vehicle", back_populates="owner")

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def is_customer(self) -> bool:
        return self.role == "CUSTOMER"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Employee(db.Model):
    """An organization employee and their configurable parking exemption."""

    __tablename__ = "employee"

    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(50), nullable=False, unique=True, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    exemption_percent = db.Column(db.Numeric(5, 2))
    vehicles = db.relationship("Vehicle", back_populates="employee")


class Vehicle(db.Model):
    """A registered vehicle, identified by its normalized registration number."""

    __tablename__ = "vehicle"
    __table_args__ = (
        db.CheckConstraint(
            "vehicle_type IN ('2-WHEELER', '3-WHEELER', '4-WHEELER')",
            name="ck_vehicle_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), nullable=False, unique=True, index=True)
    vehicle_type = db.Column(db.String(12), nullable=False)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employee.id", ondelete="SET NULL")
    )
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    employee = db.relationship("Employee", back_populates="vehicles")
    owner = db.relationship("User", back_populates="vehicles")
    sessions = db.relationship("ParkingSession", back_populates="vehicle")


class ParkingSpot(db.Model):
    """A compatible parking bay with a distance score from the entry gate."""

    __tablename__ = "parking_spot"
    __table_args__ = (
        db.CheckConstraint(
            "vehicle_type IN ('2-WHEELER', '3-WHEELER', '4-WHEELER')",
            name="ck_spot_vehicle_type",
        ),
        db.CheckConstraint(
            "status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'MAINTENANCE', 'BLOCKED')",
            name="ck_spot_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    spot_number = db.Column(db.String(20), nullable=False, unique=True)
    vehicle_type = db.Column(db.String(12), nullable=False, default="4-WHEELER")
    distance_from_entry = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="AVAILABLE", index=True)
    is_occupied = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    sessions = db.relationship("ParkingSession", back_populates="spot")

    def __repr__(self) -> str:
        return f"<ParkingSpot {self.spot_number} status={self.status}>"


@event.listens_for(ParkingSpot, "before_insert")
def _synchronize_new_spot_status(_mapper, _connection, spot):
    if spot.status is None:
        spot.status = "OCCUPIED" if spot.is_occupied else "AVAILABLE"
    spot.is_occupied = spot.status == "OCCUPIED"


@event.listens_for(ParkingSpot, "before_update")
def _synchronize_spot_status(_mapper, _connection, spot):
    state = inspect(spot)
    if state.attrs.status.history.has_changes():
        spot.is_occupied = spot.status == "OCCUPIED"
    elif state.attrs.is_occupied.history.has_changes():
        if spot.status in ("AVAILABLE", "OCCUPIED"):
            spot.status = "OCCUPIED" if spot.is_occupied else "AVAILABLE"


class ParkingSession(db.Model):
    """The auditable record of one vehicle's entry-to-exit visit."""

    __tablename__ = "parking_session"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')",
            name="ck_parking_session_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.Integer, db.ForeignKey("vehicle.id", ondelete="RESTRICT"), nullable=False
    )
    parking_spot_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_spot.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reservation_id = db.Column(
        db.Integer, db.ForeignKey("reservation.id", ondelete="SET NULL")
    )
    entry_time = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    exit_time = db.Column(db.DateTime, index=True)
    duration_minutes = db.Column(db.Integer)
    base_fare = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    employee_discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    loyalty_discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    final_fare = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    prepaid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    amount_due = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    overstay_minutes = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(12), nullable=False, default="ACTIVE", index=True)
    vehicle = db.relationship("Vehicle", back_populates="sessions")
    spot = db.relationship("ParkingSpot", back_populates="sessions")
    reservation = db.relationship(
        "Reservation", back_populates="parking_session", foreign_keys=[reservation_id]
    )


class Reservation(db.Model):
    """A time-bounded, conflict-checked reservation and advance-payment record."""

    __tablename__ = "reservation"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('PENDING_PAYMENT', 'CONFIRMED', 'CHECKED_IN', 'COMPLETED', 'CANCELLED')",
            name="ck_reservation_status",
        ),
        db.CheckConstraint(
            "payment_status IN ('PENDING', 'PAID', 'REFUNDED')",
            name="ck_reservation_payment_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.Integer, db.ForeignKey("vehicle.id", ondelete="RESTRICT"), nullable=False
    )
    parking_spot_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_spot.id", ondelete="RESTRICT"),
        nullable=False,
    )
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False, index=True)
    estimated_fare = db.Column(db.Numeric(10, 2), nullable=False)
    payment_status = db.Column(db.String(10), nullable=False, default="PENDING")
    status = db.Column(db.String(20), nullable=False, default="PENDING_PAYMENT", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    vehicle = db.relationship("Vehicle")
    spot = db.relationship("ParkingSpot")
    parking_session = db.relationship(
        "ParkingSession", back_populates="reservation", uselist=False,
        foreign_keys="ParkingSession.reservation_id",
    )
