import os
from celery import Celery
from flask import Blueprint, Flask, redirect
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import db, migrate
from .log_utils import configure_logging
from .rest import api

index_bp = Blueprint("index", __name__)

celery = Celery(__name__)


@index_bp.route("/")
def index():
    return redirect("/swagger-ui")


def _read_env_config(app: Flask):
    try:
        app.config.from_envvar("CAPTCHA_API_CONFIG")
    except (RuntimeError, KeyError) as e:
        app.logger.error(f"Failed to read environment config: {e}")


def _setup_api(app: Flask):
    api.version = app.config.get("API_VERSION", "v1")
    api.prefix = f"/api/{api.version}"
    api.init_app(app)


def _setup_celery(app: Flask):
    """Sets up Celery as a background task runner for the application."""
    if app.config.get("USE_CELERY", False):
        celery.config_from_object(app.config.get_namespace('CELERY_'))

        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask
    else:
        app.logger.warning("Celery is disabled!")


def _setup_db(app: Flask):
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    migrate.init_app(app, directory=os.path.join(app.root_path, "migrations"))


def _configure_app(app: Flask, from_env: bool = True):
    app.config.from_pyfile("captcha.cfg.example")
    if from_env:
        _read_env_config(app)


def create_app(config_override: dict = None, use_env_config: bool = True) -> Flask:
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.logger = configure_logging()

    if config_override:
        app.config.update(config_override)
    _configure_app(app, use_env_config)

    app.wsgi_app = ProxyFix(app.wsgi_app)
    CORS(app)

    _setup_db(app)
    _setup_api(app)

    # Create a Celery connection
    _setup_celery(app)

    # Register Blueprints
    app.register_blueprint(index_bp)

    return app
it