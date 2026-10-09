from functools import wraps

import jwt
from flask import current_app, request
from werkzeug.exceptions import Unauthorized

from ..extensions import db
from ..models import User


def jwt_required(fn):
    """Validate a bearer token and set the authenticated user's numeric ID."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        def reject(message: str):
            raise Unauthorized(description=message)

        parts = request.headers.get("Authorization", "").split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            reject("Missing or malformed Authorization header")
        try:
            payload = jwt.decode(
                parts[1],
                current_app.config["JWT_SECRET_KEY"],
                algorithms=[current_app.config["JWT_ALGORITHM"]],
            )
            user_id = int(payload["sub"])
        except jwt.ExpiredSignatureError:
            reject("Token has expired")
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            reject("Invalid token")

        user = db.session.get(User, user_id)
        if user is None:
            reject("Invalid token")
        if not user.is_admin:
            reject("Administrator role required")
        request.user_id = user_id
        return fn(*args, **kwargs)

    return wrapper
