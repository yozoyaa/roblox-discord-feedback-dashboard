from __future__ import annotations

from io import BytesIO
import zipfile

from flask import (
	Blueprint,
	render_template,
	send_from_directory,
	request,
	redirect,
	url_for,
	flash,
	send_file,
)

from src.services.sessions import get_active_sid_from_cookie, ensure_session_dirs
from src.utils.sharedutilities import format_dt, format_size, now_stamp, safe_filename

files_bp = Blueprint("files", __name__)


@files_bp.get("/files")
def files():
	sid = get_active_sid_from_cookie(request)
	uploads_dir = ensure_session_dirs(sid)["uploads"]

	items = []
	for p in sorted(uploads_dir.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
		st = p.stat()
		items.append({
			"name": p.name,
			"size": format_size(st.st_size),
			"modified": format_dt(st.st_mtime),
		})

	return render_template("files.html", files=items)


@files_bp.get("/download/<path:filename>")
def download(filename: str):
	sid = get_active_sid_from_cookie(request)
	uploads_dir = ensure_session_dirs(sid)["uploads"]

	filename = safe_filename(filename)
	return send_from_directory(uploads_dir, filename, as_attachment=True)


@files_bp.post("/files/download-selected")
def download_selected():
	sid = get_active_sid_from_cookie(request)
	uploads_dir = ensure_session_dirs(sid)["uploads"]

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("files.files"))

	mem = BytesIO()
	zip_name = f"crawling_files_{now_stamp()}.zip"

	with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		added = 0
		for name in selected:
			fp = uploads_dir / name
			if fp.exists() and fp.is_file():
				zf.write(fp, arcname=name)
				added += 1

	if added == 0:
		flash("File yang dipilih tidak ditemukan di server.", "danger")
		return redirect(url_for("files.files"))

	mem.seek(0)
	return send_file(
		mem,
		mimetype="application/zip",
		as_attachment=True,
		download_name=zip_name,
	)


@files_bp.post("/files/delete-selected")
def delete_selected():
	sid = get_active_sid_from_cookie(request)
	uploads_dir = ensure_session_dirs(sid)["uploads"]

	selected = request.form.getlist("selected_files")
	selected = [safe_filename(x) for x in selected if x]

	if not selected:
		flash("Tidak ada file yang dipilih.", "warning")
		return redirect(url_for("files.files"))

	deleted = 0
	for name in selected:
		fp = uploads_dir / name
		if fp.exists() and fp.is_file():
			fp.unlink()
			deleted += 1

	flash(f"Berhasil menghapus {deleted} file.", "success")
	return redirect(url_for("files.files"))
