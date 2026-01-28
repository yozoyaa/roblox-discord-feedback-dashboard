from __future__ import annotations

import threading
import uuid
from pathlib import Path
from io import BytesIO
import zipfile
import csv

from flask import (
	Blueprint,
	Response,
	current_app,
	flash,
	jsonify,
	redirect,
	render_template,
	request,
	send_file,
	send_from_directory,
	url_for,
)

from src.services.labeling import start_labeling
from src.services.sessions import get_active_sid_from_cookie, ensure_session_dirs
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

labeling_bp = Blueprint("labeling", __name__)


def _session_label_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "labeling"
	ensure_dir(d)
	return d


def _job_output_filename(job_id: str) -> str | None:
	jobs = current_app.extensions["jobs"]
	job = jobs.get(job_id)
	if job and getattr(job, "output", None):
		return safe_filename(job.output)
	return None


def _session_upload_dir(sid: str) -> Path:
	paths = ensure_session_dirs(sid)
	return paths["uploads"]


@labeling_bp.route("/labeling", methods=["GET", "POST"])
def labeling():
	sid = get_active_sid_from_cookie(request)

	if request.method == "POST":
		file = request.files.get("csv_file")
		csv_text = (request.form.get("csv_text") or "").strip()
		prefix = (request.form.get("prefix") or "labeled").strip() or "labeled"

		if not csv_text and (not file or not file.filename):
			flash("File CSV wajib diunggah.", "danger")
			return redirect(url_for("labeling.labeling"))

		filename = safe_filename(file.filename) if file else "edited.csv"
		if not filename.lower().endswith(".csv"):
			flash("File harus berformat .csv", "danger")
			return redirect(url_for("labeling.labeling"))

		upload_dir = _session_upload_dir(sid)
		input_name = f"input_labeling_{now_stamp()}_{filename}"
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
			target=start_labeling,
			args=(app_obj, job_id, sid, str(input_path), prefix),
			daemon=True,
		)
		t.start()

		flash("Job labeling dimulai. Jika salah upload, klik 'Batal Labeling'.", "success")
		return render_template("labeling.html", job_id=job_id)

	return render_template("labeling.html", job_id=None)


@labeling_bp.get("/labeling/stream/<job_id>")
def labeling_stream(job_id: str):
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


@labeling_bp.post("/labeling/cancel/<job_id>")
def cancel_labeling(job_id: str):
	jobs = current_app.extensions["jobs"]
	ok = jobs.cancel(job_id)

	if ok:
		return jsonify({"ok": True, "message": "Cancel requested."})
	return jsonify({"ok": False, "message": "Job not found or already finished."}), 400


@labeling_bp.get("/labeling/result/<job_id>")
def labeling_result(job_id: str):
	sid = get_active_sid_from_cookie(request)
	filename = _job_output_filename(job_id)
	if not filename:
		return jsonify({"ok": False, "message": "Output belum tersedia untuk job ini."}), 404

	out_dir = _session_label_dir(sid)
	fp = out_dir / filename
	if not fp.exists():
		return jsonify({"ok": False, "message": "File output tidak ditemukan."}), 404

	try:
		with fp.open("r", encoding="utf-8", newline="") as f:
			reader = csv.DictReader(f)
			headers = reader.fieldnames or []
			rows = [row for row in reader]
		return jsonify({"ok": True, "headers": headers, "rows": rows, "filename": filename})
	except Exception as e:
		return jsonify({"ok": False, "message": f"Gagal membaca output: {e}"}), 500


@labeling_bp.post("/labeling/save/<job_id>")
def labeling_save(job_id: str):
	sid = get_active_sid_from_cookie(request)
	filename = _job_output_filename(job_id)
	if not filename:
		return jsonify({"ok": False, "message": "Output belum tersedia untuk job ini."}), 404

	data = request.get_json(silent=True) or {}
	headers = data.get("headers") or []
	rows = data.get("rows") or []

	if not isinstance(headers, list) or not headers:
		return jsonify({"ok": False, "message": "Headers tidak valid."}), 400
	if not isinstance(rows, list):
		return jsonify({"ok": False, "message": "Rows tidak valid."}), 400

	out_dir = _session_label_dir(sid)
	fp = out_dir / filename
	try:
		with fp.open("w", encoding="utf-8", newline="") as f:
			writer = csv.DictWriter(f, fieldnames=headers)
			writer.writeheader()
			for r in rows:
				if not isinstance(r, dict):
					continue
				writer.writerow({k: r.get(k, "") for k in headers})
		return jsonify({"ok": True, "message": "Output berhasil disimpan.", "filename": filename})
	except Exception as e:
		return jsonify({"ok": False, "message": f"Gagal menyimpan: {e}"}), 500


@labeling_bp.get("/labeling/history")
def labeling_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_label_dir(sid)

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

	return render_template("labeling_history.html", files=items)


@labeling_bp.get("/labeling/download/<path:filename>")
def labeling_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_label_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)


@labeling_bp.post("/labeling/history/download-selected")
def labeling_history_download_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_label_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("labeling.labeling_history"))

	mem = BytesIO()
	zip_name = f"labeling_files_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = out_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("labeling.labeling_history"))

	mem.seek(0)
	return send_file(
		mem,
		mimetype="application/zip",
		as_attachment=True,
		download_name=zip_name,
	)


@labeling_bp.post("/labeling/history/delete-selected")
def labeling_history_delete_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_label_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("labeling.labeling_history"))

	deleted = 0
	for name in selected:
		fp = out_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("labeling.labeling_history"))
