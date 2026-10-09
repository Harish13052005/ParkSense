"""Shared redirect and credential helpers for the separate sign-in screens."""
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user

from ..models import User


def role_home(user: User) -> str:
    return url_for("main.home" if user.is_admin else "main.account")


def safe_next_page() -> str | None:
    next_page = request.args.get("next", "")
    parsed = urlparse(next_page)
    if (
        not parsed.scheme
        and not parsed.netloc
        and next_page.startswith("/")
        and not next_page.startswith("//")
        and "\\" not in next_page
    ):
        return next_page
    return None


def sign_in_for(role: str):
    endpoint = "auth.admin_login" if role == "ADMIN" else "auth.user_login"
    if current_user.is_authenticated:
        if current_user.role == role:
            return redirect(safe_next_page() or role_home(current_user))
        flash("Log out before switching between administrator and user accounts.", "info")
        return redirect(role_home(current_user))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.role == role and user.check_password(password):
            login_user(user)
            flash(f"Welcome, {user.username}!", "success")
            return redirect(safe_next_page() or role_home(user))
        flash("Invalid credentials for this sign-in.", "danger")
        return redirect(url_for(endpoint))

    return render_template("login.html", role=role)
