import os
import secrets
from pathlib import Path

from flask import Flask

from . import csrf
from .catalogue import Catalogue
from .google import GoogleGateway, GoogleMapsGateway

DEFAULT_DATABASE = Path(__file__).resolve().parent.parent / "cafes.db"


def create_app(config=None, google: GoogleGateway | None = None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("DATABASE") or str(DEFAULT_DATABASE),
        # Without a configured secret, sign-ins last only until the site restarts.
        SECRET_KEY=os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
        SITE_URL=os.environ.get("SITE_URL", ""),
        GOOGLE_MAPS_BROWSER_KEY=os.environ.get("GOOGLE_MAPS_BROWSER_KEY", ""),
        GOOGLE_MAPS_SERVER_KEY=os.environ.get("GOOGLE_MAPS_SERVER_KEY", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)

    app.extensions["catalogue"] = Catalogue.at(app.config["DATABASE"])
    app.extensions["google"] = google or GoogleMapsGateway(
        app.config["GOOGLE_MAPS_SERVER_KEY"]
    )
    app.jinja_env.globals["csrf_token"] = csrf.token

    from . import admin, importer, public

    app.register_blueprint(public.bp)
    app.register_blueprint(admin.bp)
    app.cli.add_command(importer.import_existing)
    return app
