"""Administrator-only web sign-in endpoint."""
from .login_support import sign_in_for


def admin_login():
    return sign_in_for("ADMIN")
