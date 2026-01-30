from __future__ import annotations
import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from src.services.sessions import ensure_session_dirs, get_active_sid_from_cookie
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, safe_filename

dashboard_bp = Blueprint("dashboard", __name__)


def _session_evaluate_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "evaluate"
	ensure_dir(d)
	return d


@dashboard_bp.get("/")
def index():
	stats = {
		"total_raw": 0,
		"total_processed": 0,
		"vocab_size": 0,
		"prob": {"positif": 0, "negatif": 0, "netral": 0},
	}
	return render_template("dashboard.html", stats=stats)


@dashboard_bp.get("/dashboard/evaluate/list")
def dashboard_evaluate_list():
	sid = get_active_sid_from_cookie(request)
	ensure_session_dirs(sid)
	out_dir = _session_evaluate_dir(sid)
	items = []
	for p in sorted(out_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
		if p.is_dir():
			continue
		st = p.stat()
		items.append(
			{
				"filename": p.name,
				"modified": format_dt(st.st_mtime),
				"size": format_size(st.st_size),
			}
		)
	return jsonify({"ok": True, "items": items})


@dashboard_bp.get("/dashboard/evaluate/load/<path:filename>")
def dashboard_evaluate_load(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_evaluate_dir(sid)
	filename = safe_filename(filename)
	target = out_dir / filename
	if not target.exists() or not target.is_file():
		return jsonify({"ok": False, "message": "File tidak ditemukan."}), 404
	try:
		payload = json.loads(target.read_text(encoding="utf-8"))
		return jsonify({"ok": True, "data": payload})
	except Exception as e:
		return jsonify({"ok": False, "message": f"Gagal membaca summary: {e}"}), 400
