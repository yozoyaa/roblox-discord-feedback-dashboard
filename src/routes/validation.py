from __future__ import annotations

import threading
import uuid
from pathlib import Path

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from src.services.validation import start_validation
from src.services.sessions import get_active_sid_from_cookie
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

validation_bp = Blueprint("validation", __name__)


def _session_validate_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "validate"
	ensure_dir(d)
	return d


def _session_upload_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "raw" / "uploads"
	ensure_dir(d)
	return d


@validation_bp.route("/validation", methods=["GET", "POST"])
def validation():
	sid = get_active_sid_from_cookie(request)

	if request.method == "POST":
		prefix = (request.form.get("prefix") or "validated").strip() or "validated"
		csv_text = (request.form.get("csv_text") or "").strip()
		file = request.files.get("csv_file")

		if not csv_text and (not file or not file.filename):
			flash("File CSV wajib diunggah.", "danger")
			return redirect(url_for("validation.validation"))

		filename = safe_filename(file.filename) if file else "edited.csv"
		if not filename.lower().endswith(".csv"):
			flash("File harus berformat .csv", "danger")
			return redirect(url_for("validation.validation"))

		upload_dir = _session_upload_dir(sid)
		input_name = f"input_validation_{now_stamp()}_{filename}"
		input_path = upload_dir / input_name
		if csv_text:
			input_path.write_text(csv_text, encoding="utf-8")
		else:
			file.save(input_path)

		jobs = current_app.extensions["jobs"]
		job_id = uuid.uuid4().hex[:10]
		jobs.create(job_id)

		app_obj = current_app._get_current_object()

		t = threading.Thread(
			target=start_validation,
			args=(app_obj, job_id, sid, str(input_path), prefix),
			daemon=True,
		)
		t.start()

		flash("Job validasi dimulai. Jika salah upload, klik 'Batal Validasi'.", "success")
		return render_template("validation.html", job_id=job_id)

	return render_template("validation.html", job_id=None)


@validation_bp.get("/validation/stream/<job_id>")
def validation_stream(job_id: str):
	jobs = current_app.extensions["jobs"]
	job = jobs.get(job_id)
	if not job:
		return Response("data: [ERROR] Job tidak ditemukan\n\n", mimetype="text/event-stream")

	def gen():
		yield "data: [SSE] connected\n\n"
		while True:
			try:
				msg = job.q.get(timeout=30)
				yield f"data: {msg}\n\n"

				if "[DONE]" in msg or "[ERROR]" in msg or "[CANCELLED]" in msg:
					break
			except Exception:
				yield "data: [SSE] keep-alive\n\n"

	return Response(gen(), mimetype="text/event-stream")


@validation_bp.post("/validation/cancel/<job_id>")
def cancel_validation(job_id: str):
	jobs = current_app.extensions["jobs"]
	ok = jobs.cancel(job_id)

	if ok:
		return jsonify({"ok": True, "message": "Cancel requested."})
	return jsonify({"ok": False, "message": "Job not found or already finished."}), 400


@validation_bp.get("/validation/history")
def validation_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_validate_dir(sid)

	items = []
	for p in sorted(out_dir.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
		st = p.stat()
		items.append(
			{
				"name": p.name,
				"size": format_size(st.st_size),
				"modified": format_dt(st.st_mtime),
			}
		)

	return render_template("validation_history.html", files=items)


@validation_bp.get("/validation/download/<path:filename>")
def validation_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_validate_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)
