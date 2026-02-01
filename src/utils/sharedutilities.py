from __future__ import annotations

from datetime import datetime
from pathlib import Path


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_log_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def format_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %B %Y %H:%M")


def format_size(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes} B"
    kb = n_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    return f"{mb:.1f} MB"


def safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    return name.strip()
