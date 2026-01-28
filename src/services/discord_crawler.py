from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import csv
import time

from flask import Flask

from src.services.discord_api import fetch_messages
from src.utils.discord_parse import extract_rating_feedback_player
from src.utils.sharedutilities import ensure_dir, now_stamp, now_log_time
from src.services.sessions import ensure_session_dirs


LOCAL_TZ = ZoneInfo("Asia/Jakarta")  # bisa kamu ganti kalau perlu


def _parse_msg_timestamp(ts: str) -> datetime | None:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_date_range(date_from: str, date_to: str):
    dt_from = None
    dt_to = None

    if date_from:
        # 00:00 local -> UTC
        d = datetime.fromisoformat(date_from)
        dt_from = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=LOCAL_TZ).astimezone(timezone.utc)

    if date_to:
        # 23:59:59 local -> UTC
        d = datetime.fromisoformat(date_to)
        dt_to = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=LOCAL_TZ).astimezone(timezone.utc)

    return dt_from, dt_to


def _keyword_match(text: str, keywords: list[str], mode: str) -> bool:
    if not keywords:
        return True
    t = text.lower().strip()
    keys = [k.lower().strip() for k in keywords if k.strip()]
    if not keys:
        return True
    if mode == "exact":
        return any(k == t for k in keys)
    return any(k in t for k in keys)


def start_discord_crawl(app: Flask, job_id: str, sid: str, bot_token: str, channel_id: str, limit: int,
                        date_from: str, date_to: str, keywords_raw: str, mode: str, prefix: str) -> None:
    with app.app_context():
        jobs = app.extensions["jobs"]

        paths = ensure_session_dirs(sid)
        uploads_dir = paths["uploads"]

        jobs.set_status(job_id, "running")
        jobs.log(job_id, f"[{now_log_time()}] [START] channel={channel_id} limit={limit}")

        dt_from, dt_to = _parse_date_range(date_from, date_to)
        if dt_from or dt_to:
            jobs.log(job_id, f"[{now_log_time()}] [INFO] Date filter aktif (local Asia/Jakarta)")

        keywords = [x.strip() for x in keywords_raw.split(",")] if keywords_raw else []

        out_name = f"{prefix}_{now_stamp()}_{channel_id}.csv"
        out_path = uploads_dir / out_name
        jobs.set_output(job_id, out_name)

        fetched = 0
        kept = 0
        before = None

        def should_cancel() -> bool:
            return jobs.is_cancel_requested(job_id)

        try:
            with out_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["player_id", "player_name", "rating", "message", "timestamp"])

                while fetched < limit:
                    if should_cancel():
                        jobs.set_status(job_id, "cancelled")
                        jobs.log(job_id, f"[{now_log_time()}] [CANCELLED] Job dibatalkan user. Cleaning up...")
                        f.close()
                        try:
                            out_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return

                    batch = min(100, limit - fetched)

                    msgs = fetch_messages(
                        bot_token=bot_token,
                        channel_id=channel_id,
                        limit=batch,
                        before=before,
                        on_log=lambda m: jobs.log(job_id, f"[{now_log_time()}] {m}"),
                        should_cancel=should_cancel,
                    )

                    if not msgs:
                        jobs.log(job_id, f"[{now_log_time()}] [INFO] Tidak ada pesan lagi / dibatalkan.")
                        break

                    fetched += len(msgs)
                    before = msgs[-1]["id"]

                    for m in msgs:
                        ts = m.get("timestamp") or ""
                        dt_msg = _parse_msg_timestamp(ts)

                        if dt_msg:
                            if dt_from and dt_msg < dt_from:
                                continue
                            if dt_to and dt_msg > dt_to:
                                continue

                        rating, feedback, player_id, player_name = extract_rating_feedback_player(m)
                        if rating is None or feedback is None:
                            continue

                        if not _keyword_match(feedback, keywords, mode):
                            continue

                        writer.writerow([player_id or "", player_name or "", rating, feedback, ts])
                        kept += 1

                    jobs.log(job_id, f"[{now_log_time()}] [PROGRESS] fetched={fetched} kept={kept}")

                    # kecilin spam rate limit
                    time.sleep(0.2)

            jobs.set_status(job_id, "done")
            jobs.log(job_id, f"[{now_log_time()}] [DONE] Output: {out_name} rows={kept}")

            if kept == 0:
                jobs.log(job_id, f"[{now_log_time()}] [WARN] Tidak ada row tersimpan. Kemungkinan format embed/content tidak cocok parser.")

        except Exception as e:
            jobs.set_status(job_id, "error")
            jobs.log(job_id, f"[{now_log_time()}] [ERROR] {type(e).__name__}: {e}")
