import os
from pathlib import Path

from flask import Flask


def create_app():
    app = Flask(__name__,
                template_folder=str(Path(__file__).parent / "templates"),
                static_folder=str(Path(__file__).parent / "static"))
    app.config["JSON_AS_ASCII"] = False
    app.config["SECRET_KEY"] = os.environ.get("BP_SECRET_KEY", "dev-only-secret-change-in-prod")
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

    from . import routes
    routes.register(app)
    return app
