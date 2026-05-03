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

    from . import db, guidelines, routes

    # Apply in-place migrations once at startup (safe to re-run)
    db.ensure_migrations()

    @app.before_request
    def _load_guideline():
        from flask import g
        gid = db.get_setting("bp_guideline", default=guidelines.DEFAULT_GUIDELINE)
        g.guideline_id = gid
        g.guideline = guidelines.get(gid)

    @app.context_processor
    def _inject_guideline():
        from flask import g
        return {"guideline": getattr(g, "guideline", guidelines.get(guidelines.DEFAULT_GUIDELINE)),
                "all_guidelines": guidelines.all_options()}

    routes.register(app)
    return app
