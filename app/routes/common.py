from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import current_user


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.admin_login", next=request.path))
        if not current_user.is_admin:
            flash("Administrator access is required for that page.", "warning")
            return redirect(url_for("main.account"))
        return view(*args, **kwargs)
    return wrapped


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.user_login", next=request.path))
        if not current_user.is_customer:
            flash("This page is for customer accounts.", "info")
            return redirect(url_for("main.home"))
        return view(*args, **kwargs)
    return wrapped
