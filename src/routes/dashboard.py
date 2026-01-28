from __future__ import annotations
from flask import Blueprint, render_template

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.get("/")
def index():
    stats = {
        "total_raw": 0,
        "total_processed": 0,
        "vocab_size": 0,
        "prob": {"positif": 0, "negatif": 0, "netral": 0},
    }
    return render_template("dashboard.html", stats=stats)
