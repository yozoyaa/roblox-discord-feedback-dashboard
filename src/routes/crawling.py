from __future__ import annotations

import threading
import uuid

from flask import (
	Blueprint,
	render_template,
	request,
	redirect,
	url_for,
	flash,
	Response,
	current_app,
	jsonify,
)

from src.services.discord_crawler import start_discord_crawl
from src.services.sessions import get_active_sid_from_cookie

crawling_bp = Blueprint("crawling", __name__)


@crawling_bp.route("/crawling", methods=["GET", "POST"])
def crawling():
	if request.method == "POST":
		# active session (workspace)
		sid = get_active_sid_from_cookie(request)

		bot_token = (request.form.get("bot_token") or "").strip()
		channel_id = (request.form.get("channel_id") or "").strip()
		limit_str = (request.form.get("limit") or "1000").strip()
		date_from = (request.form.get("date_from") or "").strip()
		date_to = (request.form.get("date_to") or "").strip()
		keywords = (request.form.get("keywords") or "").strip()
		mode = (request.form.get("mode") or "contains").strip()
		prefix = (request.form.get("prefix") or "discord_feedback").strip()

		if not bot_token:
			flash("Bot token wajib diisi.", "danger")
			return redirect(url_for("crawling.crawling"))

		if not channel_id.isdigit():
			flash("Channel ID tidak valid (harus angka).", "danger")
			return redirect(url_for("crawling.crawling"))

		try:
			limit = int(limit_str)
			if limit <= 0:
				raise ValueError
		except ValueError:
			flash("Limit harus angka > 0.", "danger")
			return redirect(url_for("crawling.crawling"))

		jobs = current_app.extensions["jobs"]
		job_id = uuid.uuid4().hex[:10]
		jobs.create(job_id)

		# pass app object so worker can use app_context safely
		app_obj = current_app._get_current_object()

		t = threading.Thread(
			target=start_discord_crawl,
			args=(
				app_obj,
				job_id,
				sid,
				bot_token,
				channel_id,
				limit,
				date_from,
				date_to,
				keywords,
				mode,
				prefix,
			),
			daemon=True,
		)
		t.start()

		flash("Job crawling dimulai. Kalau salah input, klik 'Batal Crawling'.", "success")
		return render_template("crawling.html", job_id=job_id)

	# GET
	_ = get_active_sid_from_cookie(request)
	return render_template("crawling.html", job_id=None)


@crawling_bp.get("/crawling/stream/<job_id>")
def crawling_stream(job_id: str):
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


@crawling_bp.post("/crawling/cancel/<job_id>")
def cancel_crawling(job_id: str):
	jobs = current_app.extensions["jobs"]
	ok = jobs.cancel(job_id)

	if ok:
		return jsonify({"ok": True, "message": "Cancel requested."})
	return jsonify({"ok": False, "message": "Job not found or already finished."}), 400
