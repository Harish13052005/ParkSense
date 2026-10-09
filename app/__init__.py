import click
from flask import Flask
from flask import jsonify
from datetime import timezone
from zoneinfo import ZoneInfo
from werkzeug.exceptions import Unauthorized

from .config import Config
from .extensions import csrf, db, login_manager, migrate
from .models import User
from .routes.auth import auth_bp
from .routes.main import main_bp


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    @app.template_filter("localtime")
    def localtime(value, format_string="%Y-%m-%d %H:%M"):
        if value is None:
            return ""
        return value.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(app.config["PARKING_TIMEZONE"])
        ).strftime(format_string)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.user_login"
    login_manager.login_message_category = "warning"
    csrf.init_app(app)

    @app.errorhandler(Unauthorized)
    def unauthorized(error: Unauthorized):
        return jsonify({"msg": error.description}), 401

    from .api import api_bp, auth_api_bp, workflow_bp

    csrf.exempt(api_bp)
    csrf.exempt(auth_api_bp)
    csrf.exempt(workflow_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(auth_api_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(workflow_bp)

    from .services.parking import seed_default_spots

    @app.cli.command("seed-parking")
    def seed_parking_command() -> None:
        """Create the documented 400 compatible parking bays, without duplicates."""
        created = seed_default_spots()
        db.session.commit()
        print(f"Created {created} parking spots.")

    @app.cli.command("create-admin")
    def create_admin_command() -> None:
        """Create the first administrator without exposing credentials in shell history."""
        username = click.prompt("Administrator username").strip()
        email = click.prompt("Administrator email").strip().lower()
        password = click.prompt("Administrator password", hide_input=True, confirmation_prompt=True)
        if not username or len(username) > 64 or "@" not in email or len(email) > 120:
            raise click.ClickException("Enter a valid username and email.")
        if len(password) < 8:
            raise click.ClickException("Administrator password must be at least 8 characters.")
        if User.query.filter(
            (User.username == username) | (User.email == email)
        ).first():
            raise click.ClickException("That username or email is already registered.")
        user = User(username=username, email=email, role="ADMIN")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrator {username} created.")

    @app.cli.command("set-admin-password")
    @click.argument("username")
    def set_admin_password_command(username: str) -> None:
        """Promote an existing account to administrator and reset its password."""
        username = username.strip()
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException(
                f"No account named {username!r}; create it first with create-admin."
            )
        password = click.prompt(
            "New administrator password",
            hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 8:
            raise click.ClickException("Administrator password must be at least 8 characters.")
        user.role = "ADMIN"
        user.set_password(password)
        db.session.commit()
        click.echo(f"Administrator credentials updated for {username}.")

    return app
