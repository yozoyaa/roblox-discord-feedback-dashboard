from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.utils.sharedutilities import ensure_dir, now_log_time, now_stamp

# sklearn tokenizer
from sklearn.feature_extraction.text import TfidfVectorizer

# nltk stopwords (fallback if corpus missing)
try:
	from nltk.corpus import stopwords as nltk_stopwords
except Exception:
	nltk_stopwords = None

# Optional Indonesian stemmer (recommended)
try:
	from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
except Exception:
	StemmerFactory = None

NEGATION_WORDS = {"tidak", "bukan", "jangan", "tak", "nggak", "ga", "gak", "enggak", "kagak"}

# Fallback stopwords if NLTK stopwords corpus isn't available
STOPWORDS_BASE = {
	"yang", "dan", "atau", "di", "ke", "dari", "pada", "untuk", "dengan", "karena", "bahwa",
	"itu", "ini", "saya", "aku", "kami", "kita", "kamu", "dia", "mereka",
	"ada", "jadi", "kalau", "jika", "sebagai", "agar", "supaya", "bisa", "dapat",
	"akan", "sudah", "belum", "harus",
}

# Requested step order:
# case folding > cleaning > stopword > stemming > tokenisasi
STEPS = ["case_folding", "cleaning", "stopword_removal", "stemming", "tokenization"]

RE_NON_WORD = re.compile(r"[^\w\s]+", flags=re.UNICODE)
RE_WS = re.compile(r"\s+", flags=re.UNICODE)
RE_URL = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)

# Repeated letter normalization:
# If a word has 3+ same letters in a row, remove 2 duplicates -> keep 1 char.
RE_REPEAT = re.compile(r"([a-zA-Z])\1{2,}", flags=re.UNICODE)

# sklearn tokenizer (includes 1-char tokens)
_SKLEARN_TOKENIZER = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b").build_tokenizer()

_SASTRAWI_STEMMER = None
if StemmerFactory is not None:
	try:
		_SASTRAWI_STEMMER = StemmerFactory().create_stemmer()
	except Exception:
		_SASTRAWI_STEMMER = None


def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
	with path.open("r", encoding="utf-8-sig", newline="") as f:
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


def _normalize_headers(headers: List[str]) -> List[str]:
	return [h.strip() for h in headers if h is not None and str(h).strip()]


def _header_set(headers: List[str]) -> Set[str]:
	return {h.strip().lower() for h in headers if h is not None and str(h).strip()}


def _resolve_column(headers: List[str], requested: str, kind: str) -> str:
	req = (requested or "").strip().lower()
	for h in headers:
		if (h or "").strip().lower() == req:
			return h
	raise ValueError(f"{kind} '{requested}' tidak ditemukan di header CSV.")


def _validate_schema(headers_list: List[List[str]], text_col: str, label_col: str) -> Tuple[str, str]:
	if not headers_list:
		raise ValueError("Header tidak ditemukan.")

	base_headers = _normalize_headers(headers_list[0])
	base_set = _header_set(base_headers)

	if (text_col or "").strip().lower() not in base_set:
		raise ValueError(f"TEXT_COL '{text_col}' tidak ditemukan di header CSV.")
	if (label_col or "").strip().lower() not in base_set:
		raise ValueError(f"LABEL_COL '{label_col}' tidak ditemukan di header CSV.")

	for hs in headers_list[1:]:
		hs_set = _header_set(_normalize_headers(hs))
		if hs_set != base_set:
			raise ValueError("Schema tidak konsisten antar file (kolom/header harus sama).")

	# Resolve actual header keys (case-insensitive)
	resolved_text = _resolve_column(base_headers, text_col, "TEXT_COL")
	resolved_label = _resolve_column(base_headers, label_col, "LABEL_COL")
	return resolved_text, resolved_label


def _labels_from_rows(rows: List[Dict[str, str]], label_col: str) -> Set[str]:
	out: Set[str] = set()
	for r in rows:
		val = str(r.get(label_col, "") or "").strip()
		if val:
			out.add(val)
	return out


def _reduce_repeats(s: str) -> str:
	# "gameeeee" -> "game"
	return RE_REPEAT.sub(r"\1", s)


def _clean_text(s: str) -> str:
	s = str(s or "")
	s = s.replace("\r", " ").replace("\n", " ")
	s = RE_URL.sub(" ", s)
	s = RE_NON_WORD.sub(" ", s)
	s = _reduce_repeats(s)
	s = RE_WS.sub(" ", s).strip()
	return s


def _get_stopwords(keep_negations: bool) -> Tuple[Set[str], str]:
	# Prefer NLTK Indonesian stopwords if available locally; fallback otherwise.
	if nltk_stopwords is not None:
		try:
			sw = set(nltk_stopwords.words("indonesian"))
			if keep_negations:
				sw = sw - set(NEGATION_WORDS)
			return sw, "nltk"
		except Exception:
			pass

	# Fallback
	sw = set(STOPWORDS_BASE)
	if not keep_negations:
		sw = sw | set(NEGATION_WORDS)
	return sw, "fallback"


def _tokenize_sklearn(s: str) -> List[str]:
	if not s:
		return []
	return [t for t in _SKLEARN_TOKENIZER(s) if t]


def _stem_token(tok: str) -> str:
	if _SASTRAWI_STEMMER is not None:
		try:
			return _SASTRAWI_STEMMER.stem(tok)
		except Exception:
			pass

	# Fallback: simple suffix stripping
	for suf in ("lah", "kah", "pun", "nya", "kan", "i", "an"):
		if tok.endswith(suf) and len(tok) - len(suf) >= 3:
			return tok[: -len(suf)]
	return tok


def _apply_step(
	step: str,
	headers: List[str],
	rows: List[Dict[str, Any]],
	text_col: str,
	*,
	keep_negations: bool,
) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
	new_headers = list(headers)
	summary: Dict[str, Any] = {"step": step, "rows": len(rows)}

	if step == "case_folding":
		col = "text_case"
		if col not in new_headers:
			new_headers.append(col)

		for r in rows:
			raw = str(r.get(text_col, "") or "")
			r[col] = raw.lower()

		return new_headers, rows, summary

	if step == "cleaning":
		col = "text_clean"
		src_col = "text_case" if "text_case" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		for r in rows:
			raw = str(r.get(src_col, "") or "")
			r[col] = _clean_text(raw)

		return new_headers, rows, summary

	if step == "stopword_removal":
		col = "tokens_no_stopwords"
		src_col = "text_clean" if "text_clean" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		stopwords, stopwords_source = _get_stopwords(keep_negations=keep_negations)
		summary["stopwords_source"] = stopwords_source

		for r in rows:
			text = str(r.get(src_col, "") or "")
			toks = _tokenize_sklearn(text)
			filtered = [t for t in toks if t.lower() not in stopwords]
			r[col] = " ".join(filtered)

		return new_headers, rows, summary

	if step == "stemming":
		col = "tokens_stemmed"
		src_col = "tokens_no_stopwords" if "tokens_no_stopwords" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		stemmer_source = "sastrawi" if _SASTRAWI_STEMMER is not None else "fallback"
		summary["stemmer_source"] = stemmer_source

		for r in rows:
			text = str(r.get(src_col, "") or "")
			toks = text.split()
			stemmed = [_stem_token(t) for t in toks]
			r[col] = " ".join(stemmed)

		return new_headers, rows, summary

	if step == "tokenization":
		col = "tokens"
		src_col = "tokens_stemmed" if "tokens_stemmed" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		for r in rows:
			text = str(r.get(src_col, "") or "")
			toks = _tokenize_sklearn(text)
			# UI-friendly display like your screenshot
			r[col] = ", ".join(toks)

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

	has_val = bool(val_path)
	val_headers: List[str] = []
	val_rows: List[Dict[str, str]] = []
	if has_val and val_path:
		val_headers, val_rows = _read_csv(Path(val_path))

	resolved_text_col, resolved_label_col = _validate_schema(
		[train_headers, test_headers] + ([val_headers] if has_val else []),
		text_col,
		label_col,
	)

	train_n = len(train_rows)
	test_n = len(test_rows)
	val_n = len(val_rows)

	# Your rule: Train must be bigger than the rest
	if has_val:
		if train_n <= (test_n + val_n):
			raise ValueError(
				f"Train harus lebih besar dari (Test + Val). Train={train_n}, Test={test_n}, Val={val_n}."
			)
	else:
		if train_n <= test_n:
			raise ValueError(f"Train harus lebih besar dari Test. Train={train_n}, Test={test_n}.")

	# Label safety: Test/Val labels must exist in Train
	train_labels = _labels_from_rows(train_rows, resolved_label_col)
	test_labels = _labels_from_rows(test_rows, resolved_label_col)

	if not train_labels:
		raise ValueError("Label di Train kosong / tidak terbaca. Cek LABEL_COL.")
	if not test_labels:
		raise ValueError("Label di Test kosong / tidak terbaca. Cek LABEL_COL.")

	unseen_test = sorted(test_labels - train_labels)
	if unseen_test:
		raise ValueError(f"Label di Test tidak ada di Train: {unseen_test}")

	if has_val:
		val_labels = _labels_from_rows(val_rows, resolved_label_col)
		if not val_labels:
			raise ValueError("Label di Val kosong / tidak terbaca. Cek LABEL_COL.")
		unseen_val = sorted(val_labels - train_labels)
		if unseen_val:
			raise ValueError(f"Label di Val tidak ada di Train: {unseen_val}")

	meta = {
		"job_id": job_id,
		"sid": sid,
		"prefix": prefix,
		"text_col": resolved_text_col,
		"label_col": resolved_label_col,
		"step_index": 0,
		"steps": STEPS,
		"has_val": has_val,
		"created_at": now_log_time(),
		"saved": False,
		"output_zip": "",
		"keep_negations": True,
		"counts": {"train": train_n, "test": test_n, "val": val_n},
		"labels": {"train": sorted(train_labels)},
	}

	_write_csv(_work_path(sid, job_id, "train"), train_headers, train_rows)
	_write_csv(_work_path(sid, job_id, "test"), test_headers, test_rows)
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
		return {
			"ok": True,
			"done": True,
			"saved": meta.get("saved", False),
			"output": meta.get("output_zip", ""),
		}

	step = steps[step_index]
	previews: Dict[str, Any] = {}
	summaries: Dict[str, Any] = {}

	for split in ["train", "test", "val"]:
		path = _work_path(sid, job_id, split)
		if not path.exists():
			continue

		headers, rows = _read_csv(path)
		headers, rows, summary = _apply_step(
			step,
			headers,
			rows,
			meta["text_col"],
			keep_negations=bool(meta.get("keep_negations", True)),
		)
		_write_csv(path, headers, rows)

		previews[split] = {"headers": headers, "rows": rows[:10], "total": len(rows)}
		summaries[split] = summary

	meta["step_index"] = step_index + 1
	done = meta["step_index"] >= len(steps)
	if done:
		meta["saved"] = False
		meta["output_zip"] = ""

	_save_meta(sid, job_id, meta)

	return {
		"ok": True,
		"step": step,
		"step_index": meta["step_index"],
		"steps": steps,
		"done": done,
		"saved": meta.get("saved", False),
		"previews": previews,
		"summaries": summaries,
	}


def save_output(job_id: str, sid: str) -> Dict[str, Any]:
	meta = _load_meta(sid, job_id)

	out_dir = Path(__file__).resolve().parents[2] / "data" / "sessions" / sid / "outputs" / "preprocess"
	ensure_dir(out_dir)
	stamp = now_stamp()

	files: Dict[str, str] = {}

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
