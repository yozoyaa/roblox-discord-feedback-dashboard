from __future__ import annotations

import re
from typing import Optional, Tuple


RATING_FIELD_KEYS = ("rating", "bintang", "stars", "rate")
FEEDBACK_FIELD_KEYS = ("feedback", "ulasan", "komentar", "comment", "review")
PLAYER_FIELD_KEYS = ("player", "username", "user")
PLAYER_ID_FIELD_KEYS = ("userid", "playerid", "user id", "player id")


def _extract_rating(text: str) -> Optional[int]:
    if not text:
        return None

    # digit 1-5
    m = re.search(r"\b([1-5])\b", text)
    if m:
        return int(m.group(1))

    # stars count: ⭐⭐⭐⭐
    stars = text.count("⭐")
    if 1 <= stars <= 5:
        return stars

    # "4/5"
    m2 = re.search(r"\b([1-5])\s*/\s*5\b", text)
    if m2:
        return int(m2.group(1))

    return None


def _clean_value(val: str) -> str:
    # strip markdown links [text](url) -> text
    val = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", val)
    return val.replace("\r", " ").replace("\n", " ").strip()


def _markdown_text(val: str) -> Optional[str]:
    m = re.search(r"\[([^\]]+)\]\([^)]+\)", val.strip())
    if m:
        txt = m.group(1).strip()
        return txt or None
    return None


def _strip_codeblock(val: str) -> str:
    # remove surrounding ```content``` if present
    if val.startswith("```") and val.endswith("```") and len(val) >= 6:
        return val[3:-3].strip()
    return val


def extract_rating_feedback_player(msg: dict) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    content = (msg.get("content") or "").strip()
    embeds = msg.get("embeds") or []

    rating = None
    feedback = None
    player_name = None
    player_id = None

    # from embeds fields
    for emb in embeds:
        for f in (emb.get("fields") or []):
            name = (f.get("name") or "").lower().strip()
            value_raw = (f.get("value") or "").strip()
            value_raw = _strip_codeblock(value_raw)
            value = _clean_value(value_raw)

            # prioritize ID detection so "player id" fields don't overwrite name
            if player_id is None and any(k in name for k in PLAYER_ID_FIELD_KEYS):
                v = re.sub(r"[^\d]", "", value)
                if v:
                    player_id = v
                continue

            if rating is None and any(k in name for k in RATING_FIELD_KEYS):
                r = _extract_rating(value)
                if r:
                    rating = r

            if feedback is None and any(k in name for k in FEEDBACK_FIELD_KEYS):
                if value:
                    feedback = value

            if player_name is None and any(k in name for k in PLAYER_FIELD_KEYS):
                # prefer link text if hyperlink provided
                link_txt = _markdown_text(value_raw)
                if link_txt:
                    player_name = link_txt
                elif value:
                    player_name = value

        # fallback description: can contain Player: [name](link)
        desc = (emb.get("description") or "").strip()
        if player_name is None and desc:
            link_txt = _markdown_text(desc)
            if link_txt:
                player_name = link_txt
        if feedback is None and desc:
            feedback = _strip_codeblock(desc)

        # fallback player from author name (if exists)
        if player_name is None:
            author = emb.get("author") or {}
            name = (author.get("name") or "").strip()
            if name:
                player_name = _clean_value(name)

    # fallback from content
    if rating is None:
        rating = _extract_rating(content)

    if feedback is None and len(content) >= 3:
        feedback = content

    if rating is not None and not (1 <= rating <= 5):
        rating = None

    if feedback is not None:
        feedback = feedback.replace("\r", " ").replace("\n", " ").strip()
        if feedback == "":
            feedback = None

    return rating, feedback, player_id, player_name
