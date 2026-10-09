from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import User
from .admin_login import admin_login
from .user_login import user_login

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _role_home(user: User) -> str:
    return url_for("main.home" if user.is_admin else "main.account")


auth_bp.add_url_rule(
    "/admin-login",
    endpoint="admin_login",
    view_func=admin_login,
    methods=["GET", "POST"],
)
auth_bp.add_url_rule(
    "/user-login",
    endpoint="user_login",
    view_func=user_login,
    methods=["GET", "POST"],
)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    return redirect(url_for("auth.user_login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_role_home(current_user))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if (
            not username
            or len(username) > 64
            or len(email) > 120
            or "@" not in email
            or len(password) < 8
        ):
            flash(
                "Enter a username, valid email, and password of at least 8 characters.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        if User.query.filter(
            (User.username == username) | (User.email == email)
        ).first():
            flash("Username or email already taken.", "warning")
            return redirect(url_for("auth.register"))

        user = User(username=username, email=email, role="CUSTOMER")
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username or email already taken.", "warning")
            return redirect(url_for("auth.register"))
        flash("Account created. Sign in to manage your vehicles and reservations.", "success")
        return redirect(url_for("auth.user_login"))

    return render_template("register.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))
