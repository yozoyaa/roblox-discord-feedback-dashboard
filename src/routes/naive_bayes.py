from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for

from src.services.naive_bayes import NBConfig, train_naive_bayes
from src.services.sessions import ensure_session_dirs, get_active_sid_from_cookie
from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

naive_bayes_bp = Blueprint("naive_bayes", __name__)


def _session_nb_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "naive_bayes"
	ensure_dir(d)
	return d


@naive_bayes_bp.route("/naive-bayes", methods=["GET"])
def naive_bayes_page():
	return render_template("naive_bayes.html")


@naive_bayes_bp.post("/naive-bayes/train")
def naive_bayes_train():
	sid = get_active_sid_from_cookie(request)
	paths = ensure_session_dirs(sid)

	train = request.files.get("train_file")
	test = request.files.get("test_file")
	val = request.files.get("val_file")

	text_col = (request.form.get("text_col") or "tokens_stemmed").strip()
	label_col = (request.form.get("label_col") or "sentimen").strip()
	prefix = (request.form.get("prefix") or "naive_bayes").strip() or "naive_bayes"

	if not train or not train.filename or not test or not test.filename:
		return jsonify({"ok": False, "message": "Train dan Test wajib diunggah."}), 400
	if not text_col or not label_col:
		return jsonify({"ok": False, "message": "Kolom teks/label wajib diisi."}), 400

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
		return jsonify({"ok": False, "message": str(e)}), 400

	ngram_range_str = request.form.get("ngram_range") or "1,2"
	try:
		parts = [int(x.strip()) for x in ngram_range_str.split(",") if x.strip()]
		if len(parts) != 2:
			raise ValueError()
		ngram_range = (parts[0], parts[1])
	except Exception:
		ngram_range = (1, 2)

	alpha_list_raw = request.form.get("alpha_list") or "0.1,0.5,1.0,2.0"
	alpha_list = []
	for a in alpha_list_raw.split(","):
		try:
			alpha_list.append(float(a.strip()))
		except Exception:
			continue
	alpha_single = float(request.form.get("alpha") or 1.0)

	config = NBConfig(
		text_col=text_col,
		label_col=label_col,
		min_df=int(request.form.get("min_df") or 2),
		max_df=float(request.form.get("max_df") or 0.8),
		norm=request.form.get("norm") or "l2",
		sublinear_tf=bool(request.form.get("sublinear_tf") == "on"),
		max_features=int(request.form.get("max_features") or 5000),
		ngram_range=ngram_range,
		alpha=alpha_single,
		alpha_list=alpha_list,
		fit_prior=bool(request.form.get("fit_prior", "on") == "on"),
		use_balanced_sample_weight=bool(request.form.get("use_balanced_sample_weight", "on") == "on"),
		retrain_on_train_plus_val=bool(request.form.get("retrain_on_train_plus_val", "on") == "on"),
	)

	try:
		result = train_naive_bayes(
			sid=sid,
			train_path=str(train_path),
			test_path=str(test_path),
			val_path=str(val_path) if val_path else None,
			config=config,
			prefix=prefix,
		)
		return jsonify({"ok": True, **result})
	except Exception as e:
		return jsonify({"ok": False, "message": str(e)}), 400


@naive_bayes_bp.get("/naive-bayes/history")
def naive_bayes_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_nb_dir(sid)

	items = []
	for p in sorted(out_dir.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
		st = p.stat()
		items.append(
			{
				"name": p.name,
				"size": format_size(st.st_size),
				"modified": format_dt(st.st_mtime),
			}
		)

	return render_template("naive_bayes_history.html", files=items)


@naive_bayes_bp.get("/naive-bayes/download/<path:filename>")
def naive_bayes_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_nb_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)


@naive_bayes_bp.post("/naive-bayes/history/download-selected")
def naive_bayes_history_download_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_nb_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("naive_bayes.naive_bayes_history"))

	from io import BytesIO
	import zipfile

	mem = BytesIO()
	zip_name = f"naive_bayes_files_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = out_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("naive_bayes.naive_bayes_history"))

	mem.seek(0)
	return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@naive_bayes_bp.post("/naive-bayes/history/delete-selected")
def naive_bayes_history_delete_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_nb_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("naive_bayes.naive_bayes_history"))

	deleted = 0
	for name in selected:
		fp = out_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("naive_bayes.naive_bayes_history"))
