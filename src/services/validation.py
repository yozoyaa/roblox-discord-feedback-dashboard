from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.utils.sharedutilities import ensure_dir, now_stamp, now_log_time


def _log(jobs: Any, job_id: str, msg: str) -> None:
	# kompatibel dengan JobsManager kamu:
	# - kalau ada jobs.log() pakai itu
	# - kalau tidak, fallback ke job.q.put()
	if hasattr(jobs, "log"):
		jobs.log(job_id, msg)
		return

	job = jobs.get(job_id) if hasattr(jobs, "get") else None
	if job and hasattr(job, "q"):
		job.q.put(msg)


def _set_status(jobs: Any, job_id: str, status: str) -> None:
	if hasattr(jobs, "set_status"):
		jobs.set_status(job_id, status)


def _set_output(jobs: Any, job_id: str, filename: str) -> None:
	if hasattr(jobs, "set_output"):
		jobs.set_output(job_id, filename)


def _should_cancel(jobs: Any, job_id: str) -> bool:
	if hasattr(jobs, "is_cancel_requested"):
		return bool(jobs.is_cancel_requested(job_id))

	# fallback: lihat flag di job object (kalau ada)
	job = jobs.get(job_id) if hasattr(jobs, "get") else None
	return bool(getattr(job, "cancel_requested", False))


def _find_columns(headers: list[str]) -> Tuple[str, str, Optional[str], Optional[str], Optional[str]]:
	"""
	Cari kolom rating & feedback secara fleksibel dari header CSV.
	Output: (rating_col, feedback_col, ts_col?, msg_id_col?, author_col?)
	"""
	hmap = {h.strip().lower(): h for h in headers}

	def pick(*cands: str) -> Optional[str]:
		for c in cands:
			if c in hmap:
				return hmap[c]
		return None

	rating_col = pick("rating", "stars", "score", "nilai", "bintang") or headers[0]
	feedback_col = pick("feedback", "review", "text", "message", "content", "komentar", "ulasan") or (headers[1] if len(headers) > 1 else headers[0])

	ts_col = pick("timestamp", "created_at", "date", "time", "createdat", "created")
	msg_id_col = pick("message_id", "msg_id", "id")
	author_col = pick("author", "username", "user", "author_name")

	return rating_col, feedback_col, ts_col, msg_id_col, author_col


def _parse_rating(v: str) -> Optional[int]:
	if v is None:
		return None
	s = str(v).strip()
	if s == "":
		return None

	# handle "5.0" -> 5
	try:
		f = float(s)
		n = int(f)
	except Exception:
		return None

	if 1 <= n <= 5:
		return n
	return None


def start_validation(app: Any, job_id: str, sid: str, input_csv_path: str, output_prefix: str = "validated") -> None:
	"""
	Validasi CSV:
	- rating harus 1-5
	- feedback tidak kosong
	- optional dedup berdasarkan message_id (kalau ada) atau feedback text
	Output CSV standar: rating, feedback, timestamp, message_id, author
	"""
	with app.app_context():
		jobs = app.extensions["jobs"]

		_set_status(jobs, job_id, "running")
		_log(jobs, job_id, f"[{now_log_time()}] [START] Validation job started")
		_log(jobs, job_id, f"[{now_log_time()}] [INFO] sid={sid}")
		_log(jobs, job_id, f"[{now_log_time()}] [INFO] input={input_csv_path}")

		root = Path(__file__).resolve().parents[2]
		out_dir = root / "data" / "sessions" / sid / "outputs" / "validate"
		ensure_dir(out_dir)

		out_name = f"{output_prefix}_{now_stamp()}_{sid}.csv"
		out_path = out_dir / out_name
		_set_output(jobs, job_id, out_name)

		processed = 0
		kept = 0
		invalid = 0
		seen_ids: set[str] = set()
		seen_text: set[str] = set()

		try:
			in_path = Path(input_csv_path)
			if not in_path.exists() or in_path.stat().st_size == 0:
				_set_status(jobs, job_id, "error")
				_log(jobs, job_id, f"[{now_log_time()}] [ERROR] Input file not found / empty.")
				return

			with in_path.open("r", encoding="utf-8", newline="") as fin, out_path.open("w", encoding="utf-8", newline="") as fout:
				reader = csv.DictReader(fin)
				if not reader.fieldnames:
					_set_status(jobs, job_id, "error")
					_log(jobs, job_id, f"[{now_log_time()}] [ERROR] CSV header not found.")
					return

				rating_col, feedback_col, ts_col, msg_id_col, author_col = _find_columns(reader.fieldnames)

				writer = csv.DictWriter(
					fout,
					fieldnames=["rating", "feedback", "timestamp", "message_id", "author"],
				)
				writer.writeheader()

				for row in reader:
					if _should_cancel(jobs, job_id):
						_set_status(jobs, job_id, "cancelled")
						_log(jobs, job_id, f"[{now_log_time()}] [CANCELLED] Cancel requested. Cleaning up...")
						fout.flush()
						try:
							out_path.unlink(missing_ok=True)
						except Exception:
							pass
						return

					processed += 1

					rating_raw = row.get(rating_col, "")
					feedback_raw = row.get(feedback_col, "")

					rating = _parse_rating(str(rating_raw))
					feedback = str(feedback_raw or "").strip()

					if rating is None or feedback == "":
						invalid += 1
						continue

					timestamp = ""
					if ts_col:
						timestamp = str(row.get(ts_col, "") or "").strip()

					message_id = ""
					if msg_id_col:
						message_id = str(row.get(msg_id_col, "") or "").strip()

					author = ""
					if author_col:
						author = str(row.get(author_col, "") or "").strip()

					# Dedup
					if message_id:
						if message_id in seen_ids:
							continue
						seen_ids.add(message_id)
					else:
						key = feedback.lower()
						if key in seen_text:
							continue
						seen_text.add(key)

					writer.writerow(
						{
							"rating": rating,
							"feedback": feedback,
							"timestamp": timestamp,
							"message_id": message_id,
							"author": author,
						}
					)
					kept += 1

					if processed % 200 == 0:
						_log(jobs, job_id, f"[{now_log_time()}] [PROGRESS] processed={processed} kept={kept} invalid={invalid}")

				fout.flush()

			_set_status(jobs, job_id, "done")
			_log(jobs, job_id, f"[{now_log_time()}] [DONE] output={out_name} kept={kept} invalid={invalid} processed={processed}")

			if kept == 0:
				_log(jobs, job_id, f"[{now_log_time()}] [WARN] Output 0 rows. Cek format kolom CSV input.")

		except Exception as e:
			_set_status(jobs, job_id, "error")
			_log(jobs, job_id, f"[{now_log_time()}] [ERROR] {type(e).__name__}: {e}")
			try:
				out_path.unlink(missing_ok=True)
			except Exception:
				pass
