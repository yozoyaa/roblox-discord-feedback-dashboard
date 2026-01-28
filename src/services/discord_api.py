from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any, Optional


DISCORD_API_BASE = "https://discord.com/api/v10"


def _get_json(url: str, bot_token: str) -> Any:
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "roblox-discord-feedback-dashboard/1.0",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_messages(bot_token: str, channel_id: str, limit: int = 100, before: Optional[str] = None,
                  on_log=None, should_cancel=None) -> list[dict]:
    lim = max(1, min(100, int(limit)))
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages?limit={lim}"
    if before:
        url += f"&before={before}"

    while True:
        if should_cancel and should_cancel():
            return []

        try:
            data = _get_json(url, bot_token)
            if not isinstance(data, list):
                raise RuntimeError("Discord API response bukan list messages.")
            return data

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass

            # Rate limit
            if e.code == 429 and body:
                try:
                    j = json.loads(body)
                    retry_after = float(j.get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                if on_log:
                    on_log(f"[WARN] Rate limited (429). Sleep {retry_after:.2f}s...")
                time.sleep(retry_after)
                continue

            raise RuntimeError(f"Discord API HTTP {e.code}: {body[:300]}")

        except urllib.error.URLError as e:
            raise RuntimeError(f"Discord API URL error: {e}")
