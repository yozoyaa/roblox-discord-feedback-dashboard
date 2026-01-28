from __future__ import annotations

from flask import Flask

from src.routes.dashboard import dashboard_bp
from src.routes.crawling import crawling_bp
from src.routes.files import files_bp
from src.core.job_manager import JobManager


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.secret_key = "dev-secret-key"

    # shared state (job manager) ditaruh di app.extensions
    app.extensions["jobs"] = JobManager()

    # register routes
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(crawling_bp)
    app.register_blueprint(files_bp)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
