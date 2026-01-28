from __future__ import annotations

import shutil
from flask import Blueprint, jsonify, request, make_response

from src.services.sessions import is_safe_session_id, ensure_session_dirs, sessions_root

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.get("/api/session/current")
def current_session():
	sid = request.cookies.get("sid") or "default"
	if not is_safe_session_id(sid):
		sid = "default"

	ensure_session_dirs(sid)

	resp = make_response(jsonify({"ok": True, "sid": sid}))
	resp.set_cookie("sid", sid, samesite="Lax")
	return resp


@sessions_bp.post("/api/session/switch")
def switch_session():
	data = request.get_json(silent=True) or {}
	sid = (data.get("sid") or "").strip()

	if not is_safe_session_id(sid):
		return jsonify({"ok": False, "message": "Invalid session id."}), 400

	ensure_session_dirs(sid)

	resp = make_response(jsonify({"ok": True, "sid": sid}))
	resp.set_cookie("sid", sid, samesite="Lax")
	return resp


@sessions_bp.post("/api/session/delete/<sid>")
def delete_session(sid: str):
	sid = (sid or "").strip()

	if sid == "default":
		return jsonify({"ok": False, "message": "Default session cannot be deleted."}), 400
	if not is_safe_session_id(sid):
		return jsonify({"ok": False, "message": "Invalid session id."}), 400