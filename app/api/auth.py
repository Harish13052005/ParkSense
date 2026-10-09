from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
import jwt
from datetime import datetime, timedelta, timezone

from ..models import User

auth_bp = Blueprint("auth_api", __name__, url_prefix="/api/auth")


def _create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(
                seconds=current_app.config["JWT_EXP_DELTA_SECONDS"]
            ),
        },
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
    )


@auth_bp.route('/token', methods=['POST'])
def token():
    """
    Exchange username/password for a signed JWT.
    Expected JSON payload:
        { "username": "...", "password": "..." }
    Returns:
        { "access_token": "<jwt>" }
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"msg": "A JSON object is required"}), 400
    username = str(data.get("username", "")).strip()
    password = data.get("password", "")

    if not username or not isinstance(password, str) or not password:
        return jsonify({"msg": "Missing credentials"}), 400

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({"msg": "Invalid username or password"}), 401

    return jsonify(
        {"access_token": _create_access_token(user.id), "token_type": "Bearer"}
    )


@auth_bp.route("/session-token", methods=["POST"])
def session_token():
    """Issue an in-memory API token for the signed-in browser spot manager."""
    if not current_user.is_authenticated:
        return jsonify({"msg": "A signed-in session is required"}), 401
    if not current_user.is_admin:
        return jsonify({"msg": "Administrator role required"}), 403
    return jsonify(
        {
            "access_token": _create_access_token(current_user.id),
            "token_type": "Bearer",
        }
    )