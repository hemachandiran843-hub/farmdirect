"""FarmDirect application factory."""
import os

from flask import Flask

DB_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FD_SECRET", "farmdirect-sih-prototype-key")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # -- Support running under a URL prefix (used by the sandbox preview proxy).
    #     Standalone `python run.py` runs at "/" exactly like a normal Flask app.
    prefix = os.environ.get("FD_URL_PREFIX", "")
    if prefix:
        from wsgi import PrefixMiddleware  # noqa: WPS433
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=prefix)

    # -- Blueprints --------------------------------------------------------
    from auth import bp as auth_bp
    from views import bp as views_bp
    from api import bp as api_bp
    from ivr_api import bp as ivr_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ivr_bp, url_prefix="/api")

    # -- Template helpers --------------------------------------------------
    from helpers import (CROP_META, inr, kg, status_steps, pretty_status, days_ago)

    app.jinja_env.filters["inr"] = inr
    app.jinja_env.filters["kg"] = kg
    app.jinja_env.globals.update(
        CROP_META=CROP_META,
        status_steps=status_steps,
        pretty_status=pretty_status,
        days_ago=days_ago,
    )

    # -- Global template context (cart badge) -------------------------------
    @app.context_processor
    def inject_globals():
        from flask import g, session as sess
        count = 0
        if g.get("user"):
            import db as _db
            row = _db.query("SELECT COALESCE(SUM(quantity_kg),0) n FROM cart_items WHERE user_id=?",
                            (g.user["id"],), one=True)
            count = int(row["n"]) if row else 0
        return {"cart_count": count}

    # -- Ensure DB exists & is seeded ---------------------------------------
    import db as database

    with app.app_context():
        database.init_db(force=False)
        if not database.db_is_seeded():
            import seed
            seed.seed_all()
            app.logger.info("Database seeded with sample data.")

    return app
