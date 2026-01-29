from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for

from src.services.sessions import ensure_session_dirs, get_active_sid_from_cookie
from src.services.tfidf import process_tfidf, save_summary_pdf
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

tfidf_bp = Blueprint("tfidf", __name__)


def _session_tfidf_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "tfidf"
	ensure_dir(d)
	return d


@tfidf_bp.route("/tfidf", methods=["GET", "POST"])
def tfidf():
	sid = get_active_sid_from_cookie(request)
	paths = ensure_session_dirs(sid)

	if request.method == "POST":
		action = request.form.get("action") or "start"
		prefix = (request.form.get("prefix") or "tfidf").strip() or "tfidf"
		text_col = (request.form.get("text_col") or "").strip()
		label_col = (request.form.get("label_col") or "").strip()
		mode = request.form.get("mode") or "preset"

		def parse_config() -> dict:
			ngram_min = int(request.form.get("ngram_min") or 1)
			ngram_max = int(request.form.get("ngram_max") or 2)
			max_features = int(request.form.get("max_features") or 5000)
			min_df_raw = request.form.get("min_df") or "2"
			max_df_raw = request.form.get("max_df") or "0.8"
			try:
				min_df = float(min_df_raw) if "." in min_df_raw else int(min_df_raw)
			except Exception:
				min_df = 2
			try:
				max_df = float(max_df_raw) if "." in max_df_raw else int(max_df_raw)
			except Exception:
				max_df = 0.8
			config = {
				"mode": mode,
				"ngram_range": (ngram_min, ngram_max),
				"max_features": max_features,
				"min_df": min_df,
				"max_df": max_df,
				"sublinear_tf": bool(request.form.get("sublinear_tf", "on") == "on"),
				"norm": request.form.get("norm") or "l2",
				"analyzer": request.form.get("analyzer") or "word",
				"lowercase": bool(request.form.get("lowercase") == "on"),
				"token_pattern": request.form.get("token_pattern") or r"(?u)\\b\\w\\w+\\b",
				"strip_accents": request.form.get("strip_accents") or "",
				"use_idf": bool(request.form.get("use_idf", "on") == "on"),
				"smooth_idf": bool(request.form.get("smooth_idf", "on") == "on"),
				"binary": bool(request.form.get("binary") == "on"),
				"dtype": request.form.get("dtype") or "float32",
				"stop_words": request.form.get("stop_words") or "",
				"already_tokenized": bool(request.form.get("already_tokenized") == "on"),
			}
			return config

		if action == "save":
			summary_raw = request.form.get("summary_payload") or "{}"
			try:
				summary = json.loads(summary_raw)
				if not isinstance(summary, dict):
					raise ValueError("Summary payload invalid")
			except Exception:
				flash("Payload summary tidak valid.", "danger")
				return redirect(url_for("tfidf.tfidf"))

			try:
				filename = save_summary_pdf(sid, summary, prefix)
				flash(f"Ringkasan TF-IDF disimpan ke history ({filename}).", "success")
				return redirect(url_for("tfidf.tfidf_history"))
			except Exception as e:
				flash(f"Gagal menyimpan summary: {e}", "danger")
				return redirect(url_for("tfidf.tfidf"))

		# start
		train = request.files.get("train_file")
		test = request.files.get("test_file")
		val = request.files.get("val_file")
		if not train or not train.filename or not test or not test.filename:
			flash("Train dan Test wajib diunggah.", "danger")
			return redirect(url_for("tfidf.tfidf"))
		if not text_col or not label_col:
			flash("Kolom teks dan label wajib diisi.", "danger")
			return redirect(url_for("tfidf.tfidf"))

		def save_file(fobj, name_hint: str) -> Path:
			filename = safe_filename(fobj.filename)
			if not filename.lower().endswith(".csv"):
				raise ValueError(f"File {name_hint} harus .csv")
			fp = paths["uploads"] / f"{name_hint}_{now_stamp()}_{filename}"
			fobj.save(fp)
			return fp

		try:
			train_path = save_file(train, "train")
			test_path = save_file(test, "test")
			val_path = save_file(val, "val") if val and val.filename else None
		except ValueError as e:
			flash(str(e), "danger")
			return redirect(url_for("tfidf.tfidf"))

		config = parse_config()

		try:
			summary = process_tfidf(
				sid=sid,
				train_path=str(train_path),
				test_path=str(test_path),
				val_path=str(val_path) if val_path else None,
				text_col=text_col,
				label_col=label_col,
				config=config,
				prefix=prefix,
			)
			flash("TF-IDF selesai. Review ringkasan di bawah, lalu simpan jika sudah sesuai.", "success")
			return render_template("tfidf.html", summary=summary, summary_payload=summary, prefix=prefix)
		except Exception as e:
			flash(f"Gagal menjalankan TF-IDF: {e}", "danger")
			return redirect(url_for("tfidf.tfidf"))

	return render_template("tfidf.html", summary=None, summary_payload={}, prefix="tfidf")


@tfidf_bp.get("/tfidf/history")
def tfidf_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_tfidf_dir(sid)

	items = []
	for p in sorted(out_dir.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
		st = p.stat()
		items.append(
			{
				"name": p.name,
				"size": format_size(st.st_size),
				"modified": format_dt(st.st_mtime),
			}
		)

	return render_template("tfidf_history.html", files=items)


@tfidf_bp.get("/tfidf/download/<path:filename>")
def tfidf_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_tfidf_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)


@tfidf_bp.post("/tfidf/history/download-selected")
def tfidf_history_download_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_tfidf_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("tfidf.tfidf_history"))

	from io import BytesIO
	import zipfile

	mem = BytesIO()
	zip_name = f"tfidf_files_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = out_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("tfidf.tfidf_history"))

	mem.seek(0)
	return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@tfidf_bp.post("/tfidf/history/delete-selected")
def tfidf_history_delete_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_tfidf_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("tfidf.tfidf_history"))

	deleted = 0
	for name in selected:
		fp = out_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("tfidf.tfidf_history"))
