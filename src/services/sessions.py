from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

import shutil

SAFE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_session_id(sid: str) -> bool:
	return bool(sid and SAFE_RE.match(sid))


def project_root() -> Path:
	return Path(__file__).resolve().parents[2]


def sessions_root() -> Path:
	return project_root() / "data" / "sessions"


def ensure_session_dirs(sid: str) -> Dict[str, Path]:
	root = sessions_root() / sid
	paths = {
		"base": root,
		"uploads": root / "raw" / "uploads",
		"validate": root / "outputs" / "validate",
		"preprocess": root / "outputs" / "preprocess",
		"labeling": root / "outputs" / "labeling",
		"reports": root / "reports",
	}
	for p in paths.values():
		p.mkdir(parents=True, exist_ok=True)
	return paths


def clear_session_uploads(sid: str) -> int:
	paths = ensure_session_dirs(sid)
	uploads = paths["uploads"]
	removed = 0
	for p in uploads.iterdir():
		try:
			if p.is_file():
				p.unlink()
				removed += 1
			elif p.is_dir():
				shutil.rmtree(p)
				removed += 1
		except Exception:
			continue
	return removed


def get_active_sid_from_cookie(request, default_sid: str = "default") -> str:
	sid = request.cookies.get("sid") or default_sid
	if not is_safe_session_id(sid):
		sid = default_sid
	ensure_session_dirs(sid)
	return sid
