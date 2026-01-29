from __future__ import annotations

import json
import io
import zipfile
from pathlib import Path
from typing import List

from flask import (
	Blueprint,
	current_app,
	flash,
	jsonify,
	redirect,
	render_template,
	request,
	send_from_directory,
	url_for,
)

from src.services.sessions import get_active_sid_from_cookie
from src.services.split_data import (
	read_csv_text,
	to_csv_string,
	split_rows,
	split_rows_stratified,
	make_previews,
	save_split_files,
)
from src.utils.sharedutilities import now_stamp, format_dt, format_size, safe_filename

split_bp = Blueprint("split", __name__)


def _session_split_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "split"
	d.mkdir(parents=True, exist_ok=True)
	return d


@split_bp.route("/split", methods=["GET", "POST"])
def split_data():
	sid = get_active_sid_from_cookie(request)

	if request.method == "POST":
		action = request.form.get("action") or "start"
		prefix = (request.form.get("prefix") or "split").strip() or "split"
		label_col = (request.form.get("label_col") or "").strip()
		split_mode = request.form.get("split_mode") or "none"
		ratio_choice = request.form.get("ratio_choice") or ""

		csv_text = (request.form.get("csv_text") or "").strip()
		file = request.files.get("csv_file")

		if action == "save":
			payload_raw = request.form.get("split_payload") or "[]"
			try:
				payload = json.loads(payload_raw)
				if not isinstance(payload, list) or not payload:
					raise ValueError("Payload kosong")
			except Exception:
				flash("Payload split tidak valid.", "danger")
				return redirect(url_for("split.split_data"))

			try:
				zip_name = save_split_files(_session_split_dir(sid), prefix, sid, payload)
				flash(f"Berhasil menyimpan split data ke history ({zip_name}).", "success")
				return redirect(url_for("split.split_history"))
			except Exception as e:
				flash(f"Gagal menyimpan: {e}", "danger")
				return redirect(url_for("split.split_data"))

		# START flow
		if not csv_text and (not file or not file.filename):
			flash("File CSV wajib diunggah.", "danger")
			return redirect(url_for("split.split_data"))

		if split_mode not in ("2", "3"):
			flash("Pilih mode split 2 atau 3.", "danger")
			return redirect(url_for("split.split_data"))

		filename = safe_filename(file.filename) if file else "edited.csv"
		if not filename.lower().endswith(".csv"):
			flash("File harus berformat .csv", "danger")
			return redirect(url_for("split.split_data"))

		if not csv_text:
			csv_text = file.read().decode("utf-8", errors="ignore")

		headers, rows = read_csv_text(csv_text)
		if not headers:
			flash("CSV kosong / header tidak ditemukan.", "danger")
			return redirect(url_for("split.split_data"))

		percents: List[int] = []
		if split_mode == "2":
			if ratio_choice == "50_50":
				percents = [50, 50]
			else:
				percents = [70, 30]
		elif split_mode == "3":
			if ratio_choice == "50_25_25":
				percents = [50, 25, 25]
			else:
				percents = [70, 15, 15]

		label_idx = None
		if label_col:
			for i, h in enumerate(headers):
				if h.strip().lower() == label_col.lower():
					label_idx = i
					break
			if label_idx is None:
				flash(f"Kolom label '{label_col}' tidak ditemukan di CSV.", "danger")
				return redirect(url_for("split.split_data"))

		if label_idx is not None:
			splits_rows = split_rows_stratified(rows, percents, label_index=label_idx)
		else:
			splits_rows = split_rows(rows, percents)

		names: List[str] = []
		if split_mode == "2":
			# highest percent = Train, second = Test
			names = ["Train_Data", "Test_Data"]
		else:
			names = ["Train_Data", "Val_Data", "Test_Data"]

		split_payload = []
		for name, split_part in zip(names, splits_rows):
			split_payload.append({"name": name, "csv": to_csv_string(headers, split_part), "total": len(split_part)})

		previews = make_previews(headers, list(zip(names, splits_rows)))

		return render_template(
			"split_data.html",
			job_id=None,
			previews=previews,
			split_payload=json.dumps(split_payload),
			split_mode=split_mode,
			ratio_choice=ratio_choice,
			label_col=label_col,
		)

	return render_template("split_data.html", job_id=None, previews=None, split_payload="[]", split_mode="2", ratio_choice="70_30", label_col="")


@split_bp.get("/split/history")
def split_history():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_split_dir(sid)

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

	return render_template("split_data_history.html", files=items)


@split_bp.get("/split/download/<path:filename>")
def split_download(filename: str):
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_split_dir(sid)
	filename = safe_filename(filename)
	return send_from_directory(out_dir, filename, as_attachment=True)


@split_bp.post("/split/history/download-selected")
def split_history_download_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_split_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("split.split_history"))

	mem = io.BytesIO()
	zip_name = f"split_history_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = out_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("split.split_history"))

	mem.seek(0)
	return current_app.response_class(mem.getvalue(), mimetype="application/zip", headers={"Content-Disposition": f"attachment; filename={zip_name}"})


@split_bp.post("/split/history/delete-selected")
def split_history_delete_selected():
	sid = get_active_sid_from_cookie(request)
	out_dir = _session_split_dir(sid)

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("split.split_history"))

	deleted = 0
	for name in selected:
		fp = out_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("split.split_history"))
