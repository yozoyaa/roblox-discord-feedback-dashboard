from __future__ import annotations

from flask import Flask

from src.core.job_manager import JobManager
from src.routes.dashboard import dashboard_bp
from src.routes.crawling import crawling_bp
from src.routes.files import files_bp
from src.routes.sessions import sessions_bp
from src.routes.validation import validation_bp
from src.routes.labeling import labeling_bp
from src.routes.processing import processing_bp
from src.routes.split_data import split_bp
from src.routes.tfidf import tfidf_bp
from src.routes.naive_bayes import naive_bayes_bp
from src.routes.evaluate import evaluate_bp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.secret_key = "dev-secret-key"
    app.extensions["jobs"] = JobManager()

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(crawling_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(labeling_bp)
    app.register_blueprint(processing_bp)
    app.register_blueprint(split_bp)
    app.register_blueprint(tfidf_bp)
    app.register_blueprint(naive_bayes_bp)
    app.register_blueprint(evaluate_bp)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
