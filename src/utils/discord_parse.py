from __future__ import annotations

import re
from typing import Optional, Tuple


RATING_FIELD_KEYS = ("rating", "bintang", "stars", "rate")
FEEDBACK_FIELD_KEYS = ("feedback", "ulasan", "komentar", "comment", "review")


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


def extract_rating_and_feedback(msg: dict) -> Tuple[Optional[int], Optional[str]]:
    content = (msg.get("content") or "").strip()
    embeds = msg.get("embeds") or []

    rating = None
    feedback = None

    # from embeds fields
    for emb in embeds:
        for f in (emb.get("fields") or []):
            name = (f.get("name") or "").lower().strip()
            value = (f.get("value") or "").strip()

            if rating is None and any(k in name for k in RATING_FIELD_KEYS):
                r = _extract_rating(value)
                if r:
                    rating = r

            if feedback is None and any(k in name for k in FEEDBACK_FIELD_KEYS):
                if value:
                    feedback = value

        # fallback description
        if feedback is None:
            desc = (emb.get("description") or "").strip()
            if desc:
                feedback = desc

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

    return rating, feedback
