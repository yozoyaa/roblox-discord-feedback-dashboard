from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from src.utils.sharedutilities import ensure_dir, now_log_time, now_stamp

STOPWORDS = {
	"yang", "dan", "atau", "di", "ke", "dari", "pada", "untuk", "dengan", "karena", "bahwa",
	"itu", "ini", "saya", "aku", "kami", "kita", "kamu", "dia", "mereka", "tidak", "bukan",
	"ada", "jadi", "kalau", "jika", "sebagai", "agar", "supaya", "bisa", "dapat",
	"akan", "sudah", "belum", "harus", "jangan",
}

STEPS = ["cleaning", "case_folding", "tokenization", "stopword_removal", "stemming"]


def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
	with path.open("r", encoding="utf-8", newline="") as f:
		reader = csv.DictReader(f)
		headers = reader.fieldnames or []
		rows = [row for row in reader]
	return headers, rows


def _write_csv(path: Path, headers: List[str], rows: List[Dict[str, Any]]) -> None:
	with path.open("w", encoding="utf-8", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
		writer.writeheader()
		for row in rows:
			writer.writerow({k: row.get(k, "") for k in headers})


def _clean_text(s: str) -> str:
	s = s.replace("\r", " ").replace("\n", " ")
	s = re.sub(r"[^\w\s]", " ", s)
	s = re.sub(r"\s+", " ", s).strip()
	return s


def _tokenize(s: str) -> List[str]:
	return [tok for tok in re.split(r"\s+", s) if tok]


def _stopword_remove(tokens: List[str]) -> List[str]:
	return [t for t in tokens if t.lower() not in STOPWORDS]


def _stem_token(tok: str) -> str:
	for suf in ("lah", "kah", "pun", "nya", "kan", "i", "an"):
		if tok.endswith(suf) and len(tok) - len(suf) >= 3:
			return tok[: -len(suf)]
	return tok


def _stem(tokens: List[str]) -> List[str]:
	return [_stem_token(t) for t in tokens]


def _apply_step(step: str, headers: List[str], rows: List[Dict[str, Any]], text_col: str) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
	new_headers = list(headers)
	summary: Dict[str, Any] = {"step": step, "rows": len(rows)}

	if step == "cleaning":
		col = "text_clean"
		if col not in new_headers:
			new_headers.append(col)
		for r in rows:
			raw = str(r.get(text_col, "") or "")
			r[col] = _clean_text(raw)
		return new_headers, rows, summary

	if step == "case_folding":
		col = "text_case"
		src_col = "text_clean" if "text_clean" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)
		for r in rows:
			r[col] = str(r.get(src_col, "")).lower()
		return new_headers, rows, summary

	if step == "tokenization":
		col = "tokens"
		src_col = "text_case" if "text_case" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)
		vocab: set[str] = set()
		for r in rows:
			toks = _tokenize(str(r.get(src_col, "") or ""))
			r[col] = " ".join(toks)
			vocab.update(toks)
		summary["vocab_size"] = len(vocab)
		return new_headers, rows, summary

	if step == "stopword_removal":
		col = "tokens_no_stopwords"
		src_col = "tokens" if "tokens" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)
		vocab: set[str] = set()
		for r in rows:
			toks = str(r.get(src_col, "") or "").split()
			filtered = _stopword_remove(toks)
			r[col] = " ".join(filtered)
			vocab.update(filtered)
		summary["vocab_size"] = len(vocab)
		return new_headers, rows, summary

	if step == "stemming":
		col = "tokens_stemmed"
		src_col = "tokens_no_stopwords" if "tokens_no_stopwords" in new_headers else "tokens"
		if col not in new_headers:
			new_headers.append(col)
		vocab: set[str] = set()
		for r in rows:
			toks = str(r.get(src_col, "") or "").split()
			stemmed = _stem(toks)
			r[col] = " ".join(stemmed)
			vocab.update(stemmed)
		summary["vocab_size"] = len(vocab)
		return new_headers, rows, summary

	return headers, rows, summary


def _meta_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	d = root / "data" / "sessions" / sid / "outputs" / "preprocess" / "jobs"
	ensure_dir(d)
	return d


def _meta_path(sid: str, job_id: str) -> Path:
	return _meta_dir(sid) / f"{job_id}.json"


def _work_path(sid: str, job_id: str, split_name: str) -> Path:
	return _meta_dir(sid) / f"{job_id}_{split_name}.csv"


def _validate_schema(headers_list: List[List[str]], text_col: str, label_col: str) -> None:
	if not headers_list:
		raise ValueError("Header tidak ditemukan.")
	base = [h.strip().lower() for h in headers_list[0]]
	hset = set(base)
	if text_col.lower() not in hset or label_col.lower() not in hset:
		raise ValueError("Kolom text/label tidak ditemukan di CSV.")
	for hs in headers_list[1:]:
		if [h.strip().lower() for h in hs] != base:
			raise ValueError("Schema tidak konsisten antar file (header harus sama).")


def init_job(
	job_id: str,
	sid: str,
	prefix: str,
	train_path: str,
	test_path: str,
	val_path: Optional[str],
	text_col: str,
	label_col: str,
) -> None:
	train_headers, train_rows = _read_csv(Path(train_path))
	test_headers, test_rows = _read_csv(Path(test_path))
	val_headers: List[str] = []
	val_rows: List[Dict[str, str]] = []
	has_val = bool(val_path)
	if val_path:
		val_headers, val_rows = _read_csv(Path(val_path))

	_validate_schema([train_headers, test_headers] + ([val_headers] if has_val else []), text_col, label_col)

	if len(train_rows) <= len(test_rows):
		raise ValueError("Train harus lebih besar dari Test.")
	if has_val and len(train_rows) <= (len(test_rows) + len(val_rows)):
		raise ValueError("Train harus lebih besar dari (Test + Val).")

	meta = {
		"job_id": job_id,
		"sid": sid,
		"prefix": prefix,
		"text_col": text_col,
		"label_col": label_col,
		"step_index": 0,
		"steps": STEPS,
		"has_val": has_val,
		"created_at": now_log_time(),
		"saved": False,
		"output_zip": "",
	}

	for name, headers, rows in [
		("train", train_headers, train_rows),
		("test", test_headers, test_rows),
	]:
		_write_csv(_work_path(sid, job_id, name), headers, rows)
	if has_val:
		_write_csv(_work_path(sid, job_id, "val"), val_headers, val_rows)

	_meta_path(sid, job_id).write_text(json.dumps(meta), encoding="utf-8")


def _load_meta(sid: str, job_id: str) -> Dict[str, Any]:
	mpath = _meta_path(sid, job_id)
	if not mpath.exists():
		raise RuntimeError("Job tidak ditemukan.")
	return json.loads(mpath.read_text(encoding="utf-8"))


def _save_meta(sid: str, job_id: str, meta: Dict[str, Any]) -> None:
	_meta_path(sid, job_id).write_text(json.dumps(meta), encoding="utf-8")


def _read_split(sid: str, job_id: str, split: str) -> Tuple[List[str], List[Dict[str, str]]]:
	return _read_csv(_work_path(sid, job_id, split))


def get_state(sid: str, job_id: str) -> Dict[str, Any]:
	meta = _load_meta(sid, job_id)
	previews: Dict[str, Any] = {}
	for split in ["train", "test", "val"]:
		path = _work_path(sid, job_id, split)
		if not path.exists():
			continue
		headers, rows = _read_csv(path)
		previews[split] = {"headers": headers, "rows": rows[:10], "total": len(rows)}

	return {
		"ok": True,
		"step_index": meta["step_index"],
		"steps": meta["steps"],
		"done": meta["step_index"] >= len(meta["steps"]),
		"saved": meta.get("saved", False),
		"previews": previews,
		"meta": meta,
	}


def next_step(job_id: str, sid: str) -> Dict[str, Any]:
	meta = _load_meta(sid, job_id)
	step_index = meta.get("step_index", 0)
	steps = meta.get("steps", STEPS)

	if step_index >= len(steps):
		return {"ok": True, "done": True, "saved": meta.get("saved", False), "message": "Semua step selesai.", "output": meta.get("output_zip", "")}

	step = steps[step_index]
	previews: Dict[str, Any] = {}

	for split in ["train", "test", "val"]:
		path = _work_path(sid, job_id, split)
		if not path.exists():
			continue
		headers, rows = _read_csv(path)
		headers, rows, summary = _apply_step(step, headers, rows, meta["text_col"])
		_write_csv(path, headers, rows)
		previews[split] = {"headers": headers, "rows": rows[:10], "total": len(rows)}

	meta["step_index"] = step_index + 1
	done = meta["step_index"] >= len(steps)
	if done:
		meta["output_zip"] = ""
		meta["saved"] = False

	_save_meta(sid, job_id, meta)

	return {
		"ok": True,
		"step": step,
		"step_index": meta["step_index"],
		"steps": steps,
		"done": done,
		"saved": meta.get("saved", False),
		"previews": previews,
	}


def save_output(job_id: str, sid: str) -> Dict[str, Any]:
	meta = _load_meta(sid, job_id)
	out_dir = Path(__file__).resolve().parents[2] / "data" / "sessions" / sid / "outputs" / "preprocess"
	ensure_dir(out_dir)
	stamp = now_stamp()

	files = {}
	for split in ["train", "test", "val"]:
		path = _work_path(sid, job_id, split)
		if not path.exists():
			continue
		headers, rows = _read_csv(path)
		out_name = f"{split.capitalize()}_Preprocessed_{stamp}.csv"
		_write_csv(out_dir / out_name, headers, rows)
		files[split] = out_name

	zip_name = f"{meta['prefix']}_{stamp}_{sid}.zip"
	import zipfile

	with zipfile.ZipFile(out_dir / zip_name, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		for fn in files.values():
			zf.write(out_dir / fn, arcname=fn)

	meta["saved"] = True
	meta["output_zip"] = zip_name
	_save_meta(sid, job_id, meta)

	return {"ok": True, "output": zip_name}


def cancel_job(job_id: str, sid: str) -> None:
	for split in ["train", "test", "val"]:
		try:
			_work_path(sid, job_id, split).unlink(missing_ok=True)
		except Exception:
			pass
	try:
		_meta_path(sid, job_id).unlink(missing_ok=True)
	except Exception:
		pass
