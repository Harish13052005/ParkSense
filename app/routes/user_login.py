"""Customer-only web sign-in endpoint."""
from .login_support import sign_in_for


def user_login():
    return sign_in_for("CUSTOMER")
