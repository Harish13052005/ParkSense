from flask import Blueprint
from flask_cors import CORS
from flask_restx import Api

api_bp = Blueprint("api", __name__, url_prefix="/api")
CORS(api_bp)
api = Api(
    api_bp,
    version="1.0",
    title="ParkSense Parking API",
    description="Authenticated parking spot management API",
    doc="/docs",
)

from . import parking  # noqa: E402,F401
from .auth import auth_bp as auth_api_bp
from .workflow import workflow_bp

__all__ = ["api_bp", "auth_api_bp", "workflow_bp"]
