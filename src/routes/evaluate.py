from __future__ import annotations

from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for

from src.services.evaluate import evaluate_model
from src.services.sessions import ensure_session_dirs, get_active_sid_from_cookie
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

evaluate_bp = Blueprint("evaluate", __name__)


def _session_evaluate_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "evaluate"
	ensure_dir(d)
	return d


@evaluate_bp.route("/evaluate", methods=["GET"])
def evaluate_page():
	return render_template("evaluate.html")


@evaluate_bp.post("/evaluate/run")
def evaluate_run():
	sid = get_active_sid_from_cookie(request)
	paths = ensure_session_dirs(sid)

	artifact = request.files.get("artifact_file")
	data_csv = request.files.get("data_file")
	raw_file = request.files.get("raw_file")
	pre_train_file = request.files.get("pre_train_file")
	pre_test_file = request.files.get("pre_test_file")
	pre_val_file = request.files.get("pre_val_file")
	text_col = (request.form.get("text_col") or "").strip()
	label_col = (request.form.get("label_col") or "").strip()
	prefix = (request.form.get("prefix") or "evaluate").strip() or "evaluate"

	if not artifact or not artifact.filename or not data_csv or not data_csv.filename:
		return jsonify({"ok": False, "message": "Artifact dan Data Uji wajib diunggah."}), 400

	def save_file(fobj, name_hint: str) -> Path:
		filename = safe_filename(fobj.filename)
		fp = paths["uploads"] / f"{name_hint}_{now_stamp()}_{filename}"
		fobj.save(fp)
		return fp

	try:
		artifact_path = save_file(artifact, "artifact")
		data_path = save_file(data_csv, "datauji")
		raw_path = save_file(raw_file, "raw") if raw_file and raw_file.filename else None
		pre_train_path = save_file(pre_train_file, "pretrain") if pre_train_file and pre_train_file.filename else None
		pre_test_path = save_file(pre_test_file, "pretest") if pre_test_file and pre_test_file.filename else None
		pre_val_path = save_file(pre_val_file, "preval") if pre_val_file and pre_val_file.filename else None
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400

	try:
		result = evaluate_model(
			sid=sid,
			artifact_path=str(artifact_path),
			data_path=str(data_path),
			prefix=prefix,
			text_col_override=text_col,
			label_col_override=label_col,
			raw_path=str(raw_path) if raw_path else None,
			pre_train_path=str(pre_train_path) if pre_train_path else None,
			pre_test_path=str(pre_test_path) if pre_test_path else None,
			pre_val_path=str(pre_val_path) if pre_val_path else None,
		)
		return jsonify(result)
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400


@evaluate_bp.get("/evaluate/history")
def evaluate_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_evaluate_dir(sid)

	items = []
	for p in sorted(out_dir.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
		if p.is_dir():
			continue
		st = p.stat()
		items.append(
			{
				"name": p.name,
				"size": format_size(st.st_size),
				"modified": format_dt(st.st_mtime),
			}
		)

	return render_template("evaluate_history.html", files=items)


@evaluate_bp.get("/evaluate/download/<path:filename>")
def evaluate_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_evaluate_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)


@evaluate_bp.post("/evaluate/history/download-selected")
def evaluate_history_download_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_evaluate_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("evaluate.evaluate_history"))

	from io import BytesIO
	import zipfile

	mem = BytesIO()
	zip_name = f"evaluate_files_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = out_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("evaluate.evaluate_history"))

	mem.seek(0)
	return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@evaluate_bp.post("/evaluate/history/delete-selected")
def evaluate_history_delete_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_evaluate_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("evaluate.evaluate_history"))

	deleted = 0
	for name in selected:
		fp = out_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("evaluate.evaluate_history"))
