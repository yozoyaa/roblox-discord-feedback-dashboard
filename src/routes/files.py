from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

from flask import Blueprint, render_template, send_from_directory, request, redirect, url_for, flash, send_file

from src.utils.sharedutilities import ensure_dir, format_dt, format_size, now_stamp, safe_filename

files_bp = Blueprint("files", __name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
UPLOADS_DIR = ROOT_DIR / "data" / "raw" / "uploads"
ensure_dir(UPLOADS_DIR)


@files_bp.get("/files")
def files():
    items = []
    for p in sorted(UPLOADS_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        items.append({
            "name": p.name,
            "size": format_size(st.st_size),
            "modified": format_dt(st.st_mtime),
        })
    return render_template("files.html", files=items)


@files_bp.get("/download/<path:filename>")
def download(filename: str):
    filename = safe_filename(filename)
    return send_from_directory(UPLOADS_DIR, filename, as_attachment=True)


@files_bp.post("/files/download-selected")
def download_selected():
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
            fp = UPLOADS_DIR / name
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
    selected = request.form.getlist("selected_files")
    selected = [safe_filename(x) for x in selected if x]

    if not selected:
        flash("Tidak ada file yang dipilih.", "warning")
        return redirect(url_for("files.files"))

    deleted = 0
    for name in selected:
        fp = UPLOADS_DIR / name
        if fp.exists() and fp.is_file():
            fp.unlink()
            deleted += 1

    flash(f"Berhasil menghapus {deleted} file.", "success")
    return redirect(url_for("files.files"))
