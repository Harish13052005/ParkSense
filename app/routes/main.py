"""Register the route modules that compose the main web blueprint."""
from .blueprints import main_bp
from . import admin as _admin  # noqa: F401
from . import customer as _customer  # noqa: F401
from . import public as _public  # noqa: F401

__all__ = ["main_bp"]
