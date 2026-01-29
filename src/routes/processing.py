from __future__ import annotations

import uuid
from pathlib import Path

from flask import (
	Blueprint,
	flash,
	jsonify,
	redirect,
	render_template,
	request,
	send_file,
	send_from_directory,
	url_for,
)

from src.services.processing import cancel_job, get_state, init_job, next_step, save_output
from src.services.sessions import ensure_session_dirs, get_active_sid_from_cookie
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

processing_bp = Blueprint("processing", __name__)


def _session_preprocess_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "preprocess"
	ensure_dir(d)
	return d


def _session_job_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "preprocess" / "jobs"
	ensure_dir(d)
	return d


@processing_bp.route("/processing", methods=["GET", "POST"])
def processing():
	sid = get_active_sid_from_cookie(request)

	if request.method == "POST":
		paths = ensure_session_dirs(sid)
		upload_dir = paths["uploads"]

		train = request.files.get("train_file")
		test = request.files.get("test_file")
		val = request.files.get("val_file")
		text_col = (request.form.get("text_col") or "").strip()
		label_col = (request.form.get("label_col") or "").strip()
		prefix = (request.form.get("prefix") or "preprocessed").strip() or "preprocessed"

		if not train or not train.filename or not test or not test.filename:
			flash("Train dan Test wajib diunggah.", "danger")
			return redirect(url_for("processing.processing"))
		if not text_col or not label_col:
			flash("Kolom teks dan label wajib diisi.", "danger")
			return redirect(url_for("processing.processing"))

		def save_file(fobj, name_hint: str) -> Path:
			filename = safe_filename(fobj.filename)
			if not filename.lower().endswith(".csv"):
				raise ValueError(f"File {name_hint} harus .csv")
			fp = upload_dir / f"{name_hint}_{now_stamp()}_{filename}"
			fobj.save(fp)
			return fp

		try:
			train_path = save_file(train, "train")
			test_path = save_file(test, "test")
			val_path = save_file(val, "val") if val and val.filename else None
		except ValueError as e:
			flash(str(e), "danger")
			return redirect(url_for("processing.processing"))

		job_id = uuid.uuid4().hex[:10]
		try:
			init_job(
				job_id=job_id,
				sid=sid,
				prefix=prefix,
				train_path=str(train_path),
				test_path=str(test_path),
				val_path=str(val_path) if val_path else None,
				text_col=text_col,
				label_col=label_col,
			)
		except Exception as e:
			flash(f"Gagal membuat job processing: {e}", "danger")
			return redirect(url_for("processing.processing"))

		flash("Job processing dibuat. Klik Next Step untuk mulai.", "success")
		return redirect(url_for("processing.processing", job_id=job_id))

	job_id = request.args.get("job_id") or ""
	return render_template("processing.html", job_id=job_id)


@processing_bp.get("/processing/state/<job_id>")
def processing_state(job_id: str):
	sid = get_active_sid_from_cookie(request)
	try:
		state = get_state(sid, job_id)
		return jsonify(state)
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400


@processing_bp.post("/processing/next/<job_id>")
def processing_next(job_id: str):
	sid = get_active_sid_from_cookie(request)
	try:
		result = next_step(job_id, sid)
		if not result.get("ok"):
			return jsonify(result), 400
		msg = "Step selesai."
		if result.get("done"):
			msg = "Semua step selesai. Klik Save untuk simpan output."
		return jsonify({**result, "message": msg})
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400


@processing_bp.post("/processing/save/<job_id>")
def processing_save(job_id: str):
	sid = get_active_sid_from_cookie(request)
	try:
		result = save_output(job_id, sid)
		cancel_job(job_id, sid)
		return jsonify({"ok": True, "output": result.get("output", "")})
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400


@processing_bp.post("/processing/cancel/<job_id>")
def processing_cancel(job_id: str):
	sid = get_active_sid_from_cookie(request)
	try:
		cancel_job(job_id, sid)
		return jsonify({"ok": True})
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400


@processing_bp.get("/processing/history")
def processing_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_preprocess_dir(sid)

	items = []
	for p in sorted(out_dir.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
		st = p.stat()
		items.append(
			{
				"name": p.name,
				"size": format_size(st.st_size),
				"modified": format_dt(st.st_mtime),
			}
		)

	return render_template("processing_history.html", files=items)


@processing_bp.get("/processing/download/<path:filename>")
def processing_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_preprocess_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)


@processing_bp.post("/processing/history/download-selected")
def processing_history_download_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_preprocess_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("processing.processing_history"))

	from io import BytesIO
	import zipfile

	mem = BytesIO()
	zip_name = f"processing_files_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = out_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("processing.processing_history"))

	mem.seek(0)
	return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@processing_bp.post("/processing/history/delete-selected")
def processing_history_delete_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_preprocess_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("processing.processing_history"))

	deleted = 0
	for name in selected:
		fp = out_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("processing.processing_history"))
