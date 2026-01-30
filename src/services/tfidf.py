from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.sharedutilities import ensure_dir, now_log_time, now_stamp

ALLOWED_LABELS = {"negatif", "positif"}


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
	with path.open("r", encoding="utf-8", newline="") as f:
		reader = csv.DictReader(f)
		headers = reader.fieldnames or []
		rows = [row for row in reader]
	return headers, rows


def _validate_columns(headers_list: List[List[str]], text_col: str, label_col: str) -> None:
	if not headers_list:
		raise ValueError("Header tidak ditemukan.")
	base = [h.strip().lower() for h in headers_list[0]]
	if text_col.lower() not in base or label_col.lower() not in base:
		raise ValueError("Kolom text/label tidak ditemukan di CSV.")
	for hs in headers_list[1:]:
		if [h.strip().lower() for h in hs] != base:
			raise ValueError("Schema tidak konsisten antar file (header harus sama).")


def _ngram_tokens(text: str, ngram_range: Tuple[int, int], analyzer: str = "word", already_tokenized: bool = True) -> List[str]:
	if analyzer == "char":
		raw = text.replace(" ", "")
		tokens = list(raw)
	else:
		tokens = text.split() if already_tokenized else [t for t in text.lower().split()]
	tokens = [t for t in tokens if t]
	min_n, max_n = ngram_range
	ngrams: List[str] = []
	for n in range(min_n, max_n + 1):
		if n == 1:
			ngrams.extend(tokens)
		else:
			for i in range(len(tokens) - n + 1):
				ngrams.append(" ".join(tokens[i : i + n]))
	return ngrams


def _build_vocab(
	docs: List[str],
	ngram_range: Tuple[int, int],
	min_df: float,
	max_df: float,
	max_features: int,
	analyzer: str,
	already_tokenized: bool,
) -> Dict[str, int]:
	df_counts: Dict[str, int] = {}
	for text in docs:
		seen = set(_ngram_tokens(text, ngram_range, analyzer=analyzer, already_tokenized=already_tokenized))
		for tok in seen:
			df_counts[tok] = df_counts.get(tok, 0) + 1

	n_docs = max(len(docs), 1)
	vocab_items = []
	for term, df in df_counts.items():
		if isinstance(min_df, float):
			min_ok = df / n_docs >= min_df
		else:
			min_ok = df >= min_df
		if isinstance(max_df, float):
			max_ok = df / n_docs <= max_df
		else:
			max_ok = df <= max_df
		if min_ok and max_ok:
			vocab_items.append((term, df))

	vocab_items.sort(key=lambda x: (-x[1], x[0]))
	if max_features > 0:
		vocab_items = vocab_items[:max_features]

	return {term: idx for idx, (term, _) in enumerate(vocab_items)}


def _idf(df: int, n_docs: int, smooth: bool) -> float:
	if smooth:
		return math.log((1 + n_docs) / (1 + df)) + 1
	return math.log(n_docs / max(df, 1))


def _tfidf_stats(
	docs: List[str],
	vocab: Dict[str, int],
	df_counts: Dict[str, int],
	sublinear_tf: bool,
	smooth_idf: bool,
	ngram_range: Tuple[int, int],
	analyzer: str,
	already_tokenized: bool,
	use_idf: bool,
	binary: bool,
) -> Dict[str, float]:
	n_docs = max(len(docs), 1)
	scores: Dict[str, float] = {}
	for text in docs:
		toks = _ngram_tokens(text, ngram_range, analyzer=analyzer, already_tokenized=already_tokenized)
		counts: Dict[str, int] = {}
		for tok in toks:
			if tok in vocab:
				counts[tok] = counts.get(tok, 0) + 1
		for tok, tf in counts.items():
			tf_base = 1 if binary else tf
			tf_weight = 1 + math.log(tf_base) if sublinear_tf else float(tf_base)
			idf_weight = _idf(df_counts.get(tok, 1), n_docs, smooth_idf) if use_idf else 1.0
			scores[tok] = scores.get(tok, 0.0) + tf_weight * idf_weight
	return scores


def _df_from_vocab(docs: List[str], vocab: Dict[str, int], ngram_range: Tuple[int, int], analyzer: str, already_tokenized: bool) -> Dict[str, int]:
	df_counts: Dict[str, int] = {}
	for text in docs:
		seen = set(_ngram_tokens(text, ngram_range, analyzer=analyzer, already_tokenized=already_tokenized))
		for tok in seen:
			if tok in vocab:
				df_counts[tok] = df_counts.get(tok, 0) + 1
	return df_counts


def summarize_tfidf(
	train_rows: List[Dict[str, str]],
	test_rows: List[Dict[str, str]],
	val_rows: Optional[List[Dict[str, str]]],
	text_col: str,
	label_col: str,
	config: Dict[str, Any],
) -> Dict[str, Any]:
	text_col = text_col.strip()
	label_col = label_col.strip()
	if not text_col or not label_col:
		raise ValueError("Kolom teks dan label wajib diisi.")

	train_texts = [str(r.get(text_col, "") or "") for r in train_rows]
	test_texts = [str(r.get(text_col, "") or "") for r in test_rows]
	val_texts = [str(r.get(text_col, "") or "") for r in (val_rows or [])]

	train_labels = [str(r.get(label_col, "") or "").strip().lower() for r in train_rows]
	test_labels = [str(r.get(label_col, "") or "").strip().lower() for r in test_rows]
	val_labels = [str(r.get(label_col, "") or "").strip().lower() for r in (val_rows or [])]

	train_label_set = set(train_labels)
	test_label_set = set(test_labels)
	val_label_set = set(val_labels)

	invalid_train = train_label_set - ALLOWED_LABELS
	if invalid_train:
		raise ValueError(f"Label tidak valid ditemukan di Train: {sorted(invalid_train)}. Hanya mendukung: positif/negatif.")
	if train_label_set != ALLOWED_LABELS:
		raise ValueError(f"Train harus punya kedua label: positif dan negatif. Saat ini hanya: {sorted(train_label_set)}")

	invalid_test = test_label_set - ALLOWED_LABELS
	if invalid_test:
		raise ValueError(f"Label tidak valid ditemukan di Test: {sorted(invalid_test)}. Hanya mendukung: positif/negatif.")
	invalid_val = val_label_set - ALLOWED_LABELS
	if invalid_val:
		raise ValueError(f"Label tidak valid ditemukan di Val: {sorted(invalid_val)}. Hanya mendukung: positif/negatif.")

	unseen_test = sorted(test_label_set - train_label_set)
	unseen_val = sorted(val_label_set - train_label_set)
	if unseen_test or unseen_val:
		raise ValueError(f"Label baru ditemukan. Test: {unseen_test}, Val: {unseen_val}")

	def _label_counts(labels: List[str]) -> Dict[str, int]:
		return {
			"negatif": sum(1 for l in labels if l == "negatif"),
			"positif": sum(1 for l in labels if l == "positif"),
		}

	label_counts = {
		"train": _label_counts(train_labels),
		"test": _label_counts(test_labels),
		"val": _label_counts(val_labels) if val_rows is not None else None,
	}

	pos = label_counts["train"]["positif"]
	neg = label_counts["train"]["negatif"]
	total_train = max(pos + neg, 1)
	min_label = "positif" if pos < neg else "negatif"
	min_pct = round((pos if min_label == "positif" else neg) / total_train * 100, 2)
	maj_pct = round(100 - min_pct, 2)
	label_ratio_train = {"minority_label": min_label, "minority_pct": min_pct, "majority_pct": maj_pct}

	warnings: List[str] = []
	if min_pct < 10.0:
		warnings.append("Train sangat tidak seimbang (kelas minoritas < 10%). Pertimbangkan menambah data.")
	if len(train_rows) <= len(test_rows):
		warnings.append("Saran: jumlah baris Train sebaiknya lebih besar daripada Test.")

	ngram_range = tuple(config.get("ngram_range", (1, 2)))
	max_features = int(config.get("max_features", 5000))
	min_df = config.get("min_df", 2)
	max_df = config.get("max_df", 0.8)
	sublinear_tf = bool(config.get("sublinear_tf", True))
	smooth_idf = bool(config.get("smooth_idf", True))
	use_idf = bool(config.get("use_idf", True))
	binary = bool(config.get("binary", False))
	analyzer = config.get("analyzer", "word") or "word"
	already_tokenized = bool(config.get("already_tokenized", True))

	vocab = _build_vocab(train_texts, ngram_range, min_df, max_df, max_features, analyzer, already_tokenized)
	df_counts = _df_from_vocab(train_texts, vocab, ngram_range, analyzer, already_tokenized)
	vocab_size = len(vocab)

	top_terms: List[Tuple[str, float]] = []
	if vocab_size > 0:
		scores = _tfidf_stats(
			train_texts,
			vocab,
			df_counts,
			sublinear_tf,
			smooth_idf,
			ngram_range,
			analyzer,
			already_tokenized,
			use_idf,
			binary,
		)
		top_terms = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:20]

	summary = {
		"created_at": now_log_time(),
		"vocab_size": vocab_size,
		"shapes": {
			"train": (len(train_rows), vocab_size),
			"test": (len(test_rows), vocab_size),
			"val": (len(val_rows) if val_rows else 0, vocab_size) if val_rows is not None else None,
		},
		"top_terms": [{"term": t, "score": round(s, 3)} for t, s in top_terms],
		"config": config,
		"label_set": ["negatif", "positif"],
		"label_counts": label_counts,
		"label_ratio_train": label_ratio_train,
		"warnings": warnings,
	}
	return summary


def create_pdf(summary: Dict[str, Any], out_path: Path) -> None:
	# Minimal PDF generator with single page text content
	lines = []
	lines.append("TF-IDF Summary")
	lines.append(f"Created: {summary.get('created_at', now_log_time())}")
	lines.append(f"Vocab size: {summary.get('vocab_size', 0)}")
	shapes = summary.get("shapes", {})
	lines.append(f"Train shape: {shapes.get('train')}")
	lines.append(f"Test shape: {shapes.get('test')}")
	if shapes.get("val") is not None:
		lines.append(f"Val shape: {shapes.get('val')}")
	lines.append("")
	lines.append("Label set: " + ", ".join(summary.get("label_set", [])))
	label_counts = summary.get("label_counts") or {}
	if label_counts:
		lines.append("Label counts:")
		for split in ["train", "test", "val"]:
			cnt = label_counts.get(split)
			if cnt:
				lines.append(f"- {split}: positif={cnt.get('positif',0)}, negatif={cnt.get('negatif',0)}")
	ratio = summary.get("label_ratio_train") or {}
	if ratio:
		lines.append(f"Train ratio: minority={ratio.get('minority_label')} ({ratio.get('minority_pct')}%), majority={ratio.get('majority_pct')}%")
	warnings = summary.get("warnings") or []
	if warnings:
		lines.append("Warnings:")
		for w in warnings:
			lines.append(f"- {w}")
	lines.append("")
	lines.append("Top terms:")
	for item in summary.get("top_terms", []):
		lines.append(f"- {item.get('term')}: {item.get('score')}")

	text = "\\n".join(lines)
	# Basic PDF objects
	# Escape parentheses
	text_escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
	stream = f"BT /F1 10 Tf 50 750 Td ({text_escaped}) Tj ET"
	content = stream.encode("utf-8")
	header = b"%PDF-1.4\\n"
	objects = []
	offsets = []

	def add_object(obj: str) -> None:
		offsets.append(len(header) + sum(len(o) for o in objects))
		objects.append(obj.encode("utf-8"))

	add_object("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\\n")
	add_object("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\\n")
	add_object("3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\\n")
	add_object(f"4 0 obj << /Length {len(content)} >> stream\\n{stream}\\nendstream endobj\\n")
	add_object("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Courier >> endobj\\n")

	# xref
	xref_offset = len(header) + sum(len(o) for o in objects)
	xref = "xref\\n0 6\\n0000000000 65535 f \\n"
	for off in offsets:
		xref += f"{off:010} 00000 n \\n"
	trailer = "trailer << /Size 6 /Root 1 0 R >>\\nstartxref\\n" + str(xref_offset) + "\\n%%EOF"

	with out_path.open("wb") as f:
		f.write(header)
		for obj in objects:
			f.write(obj)
		f.write(xref.encode("utf-8"))
		f.write(trailer.encode("utf-8"))


def save_summary_pdf(sid: str, summary: Dict[str, Any], prefix: str) -> str:
	out_dir = Path(__file__).resolve().parents[2] / "data" / "sessions" / sid / "outputs" / "tfidf"
	ensure_dir(out_dir)
	filename = f"{prefix}_{now_stamp()}_{sid}.pdf"
	create_pdf(summary, out_dir / filename)
	return filename


def process_tfidf(
	sid: str,
	train_path: str,
	test_path: str,
	val_path: Optional[str],
	text_col: str,
	label_col: str,
	config: Dict[str, Any],
	prefix: str,
) -> Dict[str, Any]:
	train_headers, train_rows = read_csv(Path(train_path))
	test_headers, test_rows = read_csv(Path(test_path))
	val_headers: List[str] = []
	val_rows: List[Dict[str, str]] = []

	if val_path:
		val_headers, val_rows = read_csv(Path(val_path))

	_validate_columns([train_headers, test_headers] + ([val_headers] if val_path else []), text_col, label_col)

	summary = summarize_tfidf(train_rows, test_rows, val_rows if val_path else None, text_col, label_col, config)
	summary["text_col"] = text_col
	summary["label_col"] = label_col
	summary["has_val"] = bool(val_path)
	summary["prefix"] = prefix

	return summary
