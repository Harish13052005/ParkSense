import pytest
from app import db
from app.models import User, ParkingSpot

def test_user_password_hashing():
    u = User(username="testuser", email="test@example.com")
    u.set_password("MyP@ssw0rd")
    assert u.password_hash != "MyP@ssw0rd"
    assert u.check_password("MyP@ssw0rd") is True
    assert u.check_password("wrong") is False

def test_parking_spot_crud(app):
    # Use the app's DB session directly
    with app.app_context():
        # Create
        spot = ParkingSpot(spot_number="P01")
        db.session.add(spot)
        db.session.commit()
        assert spot.id is not None

        # Read
        fetched = ParkingSpot.query.filter_by(spot_number="P01").first()
        assert fetched is not None
        assert fetched.is_occupied is False

        # Update
        fetched.is_occupied = True
        db.session.commit()
        assert ParkingSpot.query.get(fetched.id).is_occupied is True

        # Delete
        db.session.delete(fetched)
        db.session.commit()
        assert ParkingSpot.query.get(fetched.id) is None