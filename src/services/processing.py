from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.config.preprocess_config import BLACKLIST_WORD, DEFAULT_FLAGS, NORM_DICT, STOPWORDS_BASE

from src.utils.sharedutilities import ensure_dir, now_log_time, now_stamp

from sklearn.feature_extraction.text import TfidfVectorizer

try:
	from nltk.corpus import stopwords as nltk_stopwords
except Exception:
	nltk_stopwords = None

try:
	from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
except Exception:
	StemmerFactory = None

# Requested step order:
# case folding > cleaning > normalization > stopword > stemming > quality_filter > tokenisasi
STEPS = ["case_folding", "cleaning", "normalization", "stopword_removal", "stemming", "quality_filter", "tokenization"]

RE_NON_WORD = re.compile(r"[^\w\s]+", flags=re.UNICODE)
RE_WS = re.compile(r"\s+", flags=re.UNICODE)
RE_URL = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)

# Repeated letter normalization:
# If a word has 3+ same letters in a row, remove 2 duplicates -> keep 1 char.
RE_REPEAT = re.compile(r"([a-zA-Z])\1{2,}", flags=re.UNICODE)

# sklearn tokenizer (includes 1-char tokens)
_SKLEARN_TOKENIZER = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b").build_tokenizer()
ALLOWED_LABELS = {"negatif", "positif"}

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


def _label_counts(rows: List[Dict[str, Any]], label_col: str) -> Dict[str, int]:
	counts = {"negatif": 0, "positif": 0, "unknown": 0}
	for r in rows:
		val = str(r.get(label_col, "") or "").strip().lower()
		if val in ALLOWED_LABELS:
			counts[val] += 1
		else:
			counts["unknown"] += 1
	return counts


def _reduce_repeats(s: str) -> str:
	return RE_REPEAT.sub(r"\1", s)


def _clean_text(s: str) -> str:
	s = str(s or "")
	s = s.replace("\r", " ").replace("\n", " ")
	s = RE_URL.sub(" ", s)
	s = RE_NON_WORD.sub(" ", s)
	s = _reduce_repeats(s)
	s = RE_WS.sub(" ", s).strip()
	return s


def _remove_blacklist_tokens(text: str) -> Tuple[str, int]:
	tokens = text.split()
	kept: List[str] = []
	removed = 0
	for t in tokens:
		if t.lower() in BLACKLIST_WORD:
			removed += 1
			continue
		kept.append(t)
	return " ".join(kept), removed


def _apply_norm_blacklist_tokens(tokens: List[str]) -> Tuple[List[str], int, int, int]:
	out: List[str] = []
	removed_blacklist = 0
	removed_short = 0
	removed_digits = 0
	for tok in tokens:
		tlow = tok.strip().lower()
		if not tlow:
			continue
		if tlow in BLACKLIST_WORD:
			removed_blacklist += 1
			continue
		if tlow in NORM_DICT:
			tlow = NORM_DICT[tlow]
		if len(tlow) <= 2:
			removed_short += 1
			continue
		if tlow.isdigit():
			removed_digits += 1
			continue
		out.append(tlow)
	return out, removed_blacklist, removed_short, removed_digits


def _get_stopwords(use_english_stopwords: bool) -> Tuple[Set[str], str]:
    # 1) Prefer STOPWORDS_BASE if it's defined and non-empty
    base = set(globals().get("STOPWORDS_BASE") or [])
    sw: Set[str]
    source: str

    if base:
        sw = base
        source = "base"
    else:
        sw = set()
        source = "fallback"
        if nltk_stopwords is not None:
            try:
                sw = set(nltk_stopwords.words("indonesian"))
                source = "nltk"
            except Exception:
                # keep fallback empty set
                pass

    # 2) Optionally add English stopwords
    if use_english_stopwords:
        if nltk_stopwords is not None:
            try:
                eng = set(nltk_stopwords.words("english"))
                sw |= eng
                source = f"{source}+english"
            except Exception:
                source = f"{source}+eng_fallback"
        else:
            source = f"{source}+eng_fallback"

    return sw, source


def _tokenize_sklearn(s: str) -> List[str]:
	if not s:
		return []
	return [t for t in _SKLEARN_TOKENIZER(s) if t]


def _collapse_repeat(tok: str) -> str:
	m = re.match(r"^([a-z]{2,4})\1+$", tok)
	if m:
		return m.group(1)
	return tok


def _normalize_tokens(
	text: str,
	*,
	normalize_slang: bool,
) -> List[str]:
	if not text:
		return []
	toks = _tokenize_sklearn(text)
	out: List[str] = []
	for tok in toks:
		tlow = _collapse_repeat(tok.lower())
		if tlow == "nya":
			continue
		if normalize_slang and tlow in NORM_DICT:
			out.append(NORM_DICT[tlow])
			continue
		out.append(tlow)
	return out


def _quality_filter_rows(
	rows: List[Dict[str, Any]],
	text_col: str,
	src_col: str,
	*,
	drop_invalid_rows: bool,
	cleanup_digits: bool,
	cleanup_spam_tokens: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
	re_alpha = re.compile(r"[A-Za-z]", flags=re.UNICODE)
	whitelist_short = {"ok", "gg", "no"}
	allow_tokens = {"rpg", "p2w", "hp", "vr", "pls", "gg", "dc", "ty", "dll"}
	reasons: Dict[str, int] = {}
	samples: List[Dict[str, str]] = []
	kept: List[Dict[str, Any]] = []
	removed_token_samples: List[str] = []
	tokens_removed_total = 0

	def _token_cleanup(tokens: List[str], *, remove_digits: bool, remove_spam: bool) -> List[str]:
		nonlocal tokens_removed_total, removed_token_samples
		out_tokens: List[str] = []
		for tok in tokens:
			t = tok.strip()
			if not t:
				continue
			t_lower = t.lower()
			if t_lower in whitelist_short:
				out_tokens.append(t)
				continue
			if remove_digits and t.isdigit():
				tokens_removed_total += 1
				if len(removed_token_samples) < 5:
					removed_token_samples.append(t)
				continue
			if remove_spam:
				unique_chars = len(set(t_lower))
				if len(t) >= 6 and unique_chars <= 2:
					tokens_removed_total += 1
					if len(removed_token_samples) < 5:
						removed_token_samples.append(t)
					continue
				if len(t) >= 5 and not re.search(r"[aiueo]", t_lower):
					if t_lower in allow_tokens:
						out_tokens.append(t)
						continue
					tokens_removed_total += 1
					if len(removed_token_samples) < 5:
						removed_token_samples.append(t)
					continue
				if 3 <= len(t) <= 4 and not re.search(r"[aiueo]", t_lower):
					if t_lower in NORM_DICT or t_lower in allow_tokens:
						out_tokens.append(t)
						continue
					tokens_removed_total += 1
					if len(removed_token_samples) < 5:
						removed_token_samples.append(t)
					continue
				if len(set(t_lower)) == 1 and len(t) >= 3:
					tokens_removed_total += 1
					if len(removed_token_samples) < 5:
						removed_token_samples.append(t)
					continue
				if not re.search(r"[a-zA-Z]", t):
					tokens_removed_total += 1
					if len(removed_token_samples) < 5:
						removed_token_samples.append(t)
					continue
			out_tokens.append(t)
		return out_tokens

	for r in rows:
		raw_original = str(r.get(text_col, "") or "")
		final_text = str(r.get(src_col, "") or "").strip()
		tokens_raw = final_text.split()
		tokens = _token_cleanup(tokens_raw, remove_digits=cleanup_digits, remove_spam=cleanup_spam_tokens)
		final_text_cleaned = " ".join(tokens)
		r[src_col] = final_text_cleaned
		token_count = len(tokens)
		chars = final_text_cleaned.replace(" ", "")

		reason = None
		if not final_text_cleaned or token_count == 0:
			reason = "empty"
		elif not re_alpha.search(final_text_cleaned):
			reason = "no_alpha"
		else:
			total_chars = len(chars)
			digit_count = sum(1 for c in chars if c.isdigit())
			if total_chars > 0 and (digit_count / total_chars) > 0.85:
				reason = "digit_heavy"
			elif token_count == 1:
				t0 = tokens[0] if tokens else ""
				if len(t0) <= 2 and t0.lower() not in whitelist_short:
					reason = "single_too_short"
				else:
					unique_chars = len(set(t0.lower()))
					no_vowel = len(t0) >= 5 and not re.search(r"[aiueo]", t0.lower())
					repetitive = len(t0) >= 8 and unique_chars <= 2
					single_char_only = len(set(t0.lower())) == 1 and len(t0) >= 3
					collapsed = _collapse_repeat(t0.lower())
					if no_vowel or repetitive or single_char_only or collapsed != t0.lower():
						reason = "single_spam"
			elif any(len(t) >= 20 for t in tokens):
				reason = "token_too_long"
			elif token_count >= 3:
				one_char = sum(1 for t in tokens if len(t) == 1)
				if (one_char / token_count) > 0.8:
					reason = "too_many_single_char"

		if reason:
			reasons[reason] = reasons.get(reason, 0) + 1
			if len(samples) < 3:
				samples.append({"reason": reason, "original": raw_original, "final": final_text_cleaned})
			if drop_invalid_rows:
				continue

		kept.append(r)

	return kept, {
		"dropped_rows": len(rows) - len(kept) if drop_invalid_rows else 0,
		"kept_rows": len(kept),
		"reason_counts": reasons,
		"samples": samples,
		"tokens_removed_total": tokens_removed_total,
		"removed_token_samples": removed_token_samples[:5],
		"skipped": not drop_invalid_rows,
	}


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
	normalize_slang: bool,
	drop_invalid_rows: bool,
	cleanup_digits: bool,
	cleanup_spam_tokens: bool,
	use_english_stopwords: bool,
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

		removed_total = 0
		norm_applied = 0
		for r in rows:
			raw = str(r.get(src_col, "") or "")
			cleaned = _clean_text(raw)
			parts = cleaned.split()
			normalized: List[str] = []
			for p in parts:
				plow = p.lower()
				if plow in NORM_DICT:
					normalized.append(NORM_DICT[plow])
					norm_applied += 1
				else:
					normalized.append(p)
			normalized_text = " ".join(normalized)
			normalized_text, removed = _remove_blacklist_tokens(normalized_text)
			removed_total += removed
			r[col] = normalized_text

		summary["blacklist_removed_tokens"] = removed_total
		summary["norm_applied"] = norm_applied

		return new_headers, rows, summary

	if step == "normalization":
		col = "text_normalized"
		src_col = "text_clean" if "text_clean" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		for r in rows:
			text = str(r.get(src_col, "") or "")
			toks = _normalize_tokens(
				text,
				normalize_slang=normalize_slang,
			)
			r[col] = " ".join(toks)

		return new_headers, rows, summary

	if step == "stopword_removal":
		col = "tokens_no_stopwords"
		src_col = "text_normalized" if "text_normalized" in new_headers else "text_clean" if "text_clean" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		stopwords, stopwords_source = _get_stopwords(use_english_stopwords=use_english_stopwords)
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
		new_rows: List[Dict[str, Any]] = []
		removed_blacklist = 0
		removed_short = 0
		removed_digits = 0
		rows_before = len(rows)
		rows_dropped = 0

		for r in rows:
			text = str(r.get(src_col, "") or "")
			toks = text.split()
			stemmed = [_stem_token(t) for t in toks]
			final_tokens: List[str] = []
			for t in stemmed:
				tlow = t.lower()
				if tlow in NORM_DICT:
					tlow = NORM_DICT[tlow]
				if tlow in BLACKLIST_WORD:
					removed_blacklist += 1
					continue
				if len(tlow) <= 2:
					removed_short += 1
					continue
				if tlow.isdigit():
					removed_digits += 1
					continue
				final_tokens.append(tlow)
			if not final_tokens:
				rows_dropped += 1
				if drop_invalid_rows:
					continue
			r[col] = " ".join(final_tokens)
			new_rows.append(r)

		summary["rows_before"] = rows_before
		summary["rows_after"] = len(new_rows)
		summary["tokenization_rows_before"] = rows_before
		summary["tokenization_rows_after"] = len(new_rows)
		summary["rows_dropped_empty_tokens"] = rows_dropped if drop_invalid_rows else 0
		summary["dropped_rows"] = rows_dropped if drop_invalid_rows else 0
		summary["tokens_removed_blacklist"] = removed_blacklist
		summary["tokens_removed_short"] = removed_short
		summary["tokens_removed_digits"] = removed_digits

		return new_headers, new_rows, summary

	if step == "quality_filter":
		# Choose most processed text available
		src_col = "tokens_stemmed" if "tokens_stemmed" in new_headers else "tokens_no_stopwords" if "tokens_no_stopwords" in new_headers else "text_normalized" if "text_normalized" in new_headers else text_col
		filtered_rows, q_summary = _quality_filter_rows(
			rows,
			text_col=text_col,
			src_col=src_col,
			drop_invalid_rows=drop_invalid_rows,
			cleanup_digits=cleanup_digits,
			cleanup_spam_tokens=cleanup_spam_tokens,
		)
		q_summary["rows_before"] = len(rows)
		q_summary["rows_after"] = len(filtered_rows)
		summary.update(q_summary)
		return new_headers, filtered_rows, summary

	if step == "tokenization":
		col = "tokens"
		src_col = "tokens_stemmed" if "tokens_stemmed" in new_headers else text_col
		if col not in new_headers:
			new_headers.append(col)

		new_rows: List[Dict[str, Any]] = []
		rows_before = len(rows)
		removed_blacklist = 0
		removed_short = 0
		removed_digits = 0
		norm_applied = 0
		rows_dropped = 0

		for r in rows:
			text = str(r.get(src_col, "") or "")
			toks = _tokenize_sklearn(text)
			processed: List[str] = []
			for tok in toks:
				tlow = _collapse_repeat(tok.lower().strip())
				if not tlow:
					continue
				if tlow in NORM_DICT:
					norm_val = NORM_DICT[tlow]
					norm_applied += 1
					for part in norm_val.split():
						if part:
							processed.append(part)
					continue
				if tlow in BLACKLIST_WORD:
					removed_blacklist += 1
					continue
				if len(tlow) <= 2:
					removed_short += 1
					continue
				if tlow.isdigit():
					removed_digits += 1
					continue
				processed.append(tlow)

			processed, extra_blk, extra_short, extra_digits = _apply_norm_blacklist_tokens(processed)
			removed_blacklist += extra_blk
			removed_short += extra_short
			removed_digits += extra_digits

			if not processed:
				rows_dropped += 1
				if drop_invalid_rows:
					continue
			r[col] = " ".join(processed)
			new_rows.append(r)

		summary["rows_before"] = rows_before
		summary["rows_after"] = len(new_rows)
		summary["tokenization_rows_before"] = rows_before
		summary["tokenization_rows_after"] = len(new_rows)
		summary["tokenization_rows_dropped_empty"] = rows_dropped if drop_invalid_rows else 0
		summary["dropped_rows"] = rows_dropped if drop_invalid_rows else 0
		summary["tokenization_blacklist_removed"] = removed_blacklist
		summary["tokenization_short_removed"] = removed_short
		summary["tokenization_removed_digits"] = removed_digits
		summary["tokenization_norm_applied"] = norm_applied

		return new_headers, new_rows, summary

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
	*,
	normalize_slang: bool = DEFAULT_FLAGS["normalize_slang"],
	drop_invalid_rows: bool = DEFAULT_FLAGS["drop_invalid_rows"],
	cleanup_digits: bool = DEFAULT_FLAGS["cleanup_digits"],
	cleanup_spam_tokens: bool = DEFAULT_FLAGS["cleanup_spam_tokens"],
	use_english_stopwords: bool = DEFAULT_FLAGS["use_english_stopwords"],
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
	train_labels_lower = {l.lower() for l in train_labels}
	test_labels_lower = {l.lower() for l in test_labels}

	if not train_labels:
		raise ValueError("Label di Train kosong / tidak terbaca. Cek LABEL_COL.")
	if not test_labels:
		raise ValueError("Label di Test kosong / tidak terbaca. Cek LABEL_COL.")

	invalid_train = train_labels_lower - ALLOWED_LABELS
	if invalid_train:
		raise ValueError(f"Label tidak valid ditemukan di Train: {sorted(invalid_train)}. Hanya mendukung: negatif/positif.")
	if train_labels_lower != ALLOWED_LABELS:
		raise ValueError(f"Train harus memiliki kedua label (negatif dan positif). Saat ini hanya: {sorted(train_labels_lower)}")

	unseen_test = sorted(test_labels_lower - train_labels_lower)
	if unseen_test:
		raise ValueError(f"Label di Test tidak ada di Train: {unseen_test}")

	if has_val:
		val_labels = _labels_from_rows(val_rows, resolved_label_col)
		val_labels_lower = {l.lower() for l in val_labels}
		if not val_labels:
			raise ValueError("Label di Val kosong / tidak terbaca. Cek LABEL_COL.")
		unseen_val = sorted(val_labels_lower - train_labels_lower)
		if unseen_val:
			raise ValueError(f"Label di Val tidak ada di Train: {unseen_val}")
		invalid_val = val_labels_lower - ALLOWED_LABELS
		if invalid_val:
			raise ValueError(f"Label tidak valid ditemukan di Val: {sorted(invalid_val)}. Hanya mendukung: negatif/positif.")

	invalid_test = test_labels_lower - ALLOWED_LABELS
	if invalid_test:
		raise ValueError(f"Label tidak valid ditemukan di Test: {sorted(invalid_test)}. Hanya mendukung: negatif/positif.")

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
		"normalize_slang": bool(normalize_slang),
		"drop_invalid_rows": bool(drop_invalid_rows),
		"cleanup_digits": bool(cleanup_digits),
		"cleanup_spam_tokens": bool(cleanup_spam_tokens),
		"use_english_stopwords": bool(use_english_stopwords),
		"counts": {"train": train_n, "test": test_n, "val": val_n},
		"labels": {"train": sorted(train_labels)},
		"label_stats_before": {
			"train": _label_counts(train_rows, resolved_label_col),
			"test": _label_counts(test_rows, resolved_label_col),
			"val": _label_counts(val_rows, resolved_label_col) if has_val else {},
		},
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
	quality_cache: Dict[str, Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]] = {}
	label_sets_after: Dict[str, Set[str]] = {}
	label_stats: Dict[str, Dict[str, int]] = {}
	log_lines: List[str] = []

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
			normalize_slang=bool(meta.get("normalize_slang", True)),
			drop_invalid_rows=bool(meta.get("drop_invalid_rows", True)),
			cleanup_digits=bool(meta.get("cleanup_digits", True)),
			cleanup_spam_tokens=bool(meta.get("cleanup_spam_tokens", True)),
			use_english_stopwords=bool(meta.get("use_english_stopwords", False)),
		)

		if step == "quality_filter":
			quality_cache[split] = (headers, rows, summary)
			label_sets_after[split] = _labels_from_rows(rows, meta["label_col"])
		else:
			_write_csv(path, headers, rows)
			previews[split] = {"headers": headers, "rows": rows[:10], "total": len(rows)}
			summaries[split] = summary
		label_stats[split] = _label_counts(rows, meta["label_col"])

		# Build per-split log lines
		if summary:
			lines: List[str] = []
			before = summary.get("rows_before") or summary.get("tokenization_rows_before") or summary.get("rows")
			after = summary.get("rows_after") or summary.get("tokenization_rows_after") or summary.get("rows")
			dropped = summary.get("dropped_rows") or summary.get("tokenization_rows_dropped_empty")
			if before or after or dropped:
				lines.append(f"[{step}] {split}: before={before if before is not None else '-'} after={after if after is not None else '-'} dropped={dropped if dropped is not None else 0}")
			if "tokenization_blacklist_removed" in summary or "tokenization_short_removed" in summary:
				blk = summary.get("tokenization_blacklist_removed", 0)
				sh = summary.get("tokenization_short_removed", 0)
				norm_applied = summary.get("tokenization_norm_applied", 0)
				lines.append(f"  tokenization cleanup: blacklist_removed={blk}, short_removed={sh}, norm_applied={norm_applied}")
			if "tokens_removed_total" in summary:
				lines.append(f"  tokens_removed_total={summary.get('tokens_removed_total', 0)}")
			reasons = summary.get("reason_counts") or {}
			if reasons:
				top = sorted(reasons.items(), key=lambda x: -x[1])[:3]
				parts = [f"{k}={v}" for k, v in top]
				lines.append(f"  reasons: {', '.join(parts)}")
			samples = summary.get("samples") or []
			for smp in samples[:2]:
				orig = str(smp.get("original", ""))[:80]
				fin = str(smp.get("final", ""))[:80]
				lines.append(f"  sample ({split}) reason={smp.get('reason','')}: \"{orig}\" -> \"{fin}\"")
			log_lines.extend(lines)

	# Post-step label safety check specifically after quality_filter
	if step == "quality_filter":
		train_labels = label_sets_after.get("train", set())
		test_labels = label_sets_after.get("test", set())
		val_labels = label_sets_after.get("val", set())
		train_lower = {l.lower() for l in train_labels}
		test_lower = {l.lower() for l in test_labels} if test_labels is not None else set()
		val_lower = {l.lower() for l in val_labels} if val_labels is not None else set()

		if not train_labels:
			raise ValueError("Setelah quality filter, label Train kosong atau semua baris terhapus.")
		if train_lower - ALLOWED_LABELS:
			raise ValueError(f"Setelah quality filter, ditemukan label tidak valid di Train: {sorted(train_lower - ALLOWED_LABELS)}")
		if train_lower != ALLOWED_LABELS:
			missing = sorted(ALLOWED_LABELS - train_lower)
			raise ValueError(f"Setelah quality filter, label {missing} habis terhapus. Kurangi filter atau tambah data.")

		if test_labels is not None:
			invalid_test_after = sorted(test_lower - ALLOWED_LABELS)
			if invalid_test_after:
				raise ValueError(f"Setelah quality filter, ditemukan label tidak valid di Test: {invalid_test_after}")
			unseen_test = sorted(test_lower - train_lower)
			if unseen_test:
				raise ValueError(f"Setelah quality filter, label Test tidak ada di Train: {unseen_test}")

		if meta.get("has_val") and val_labels is not None:
			invalid_val_after = sorted(val_lower - ALLOWED_LABELS)
			if invalid_val_after:
				raise ValueError(f"Setelah quality filter, ditemukan label tidak valid di Val: {invalid_val_after}")
			unseen_val = sorted(val_lower - train_lower)
			if unseen_val:
				raise ValueError(f"Setelah quality filter, label Val tidak ada di Train: {unseen_val}")

		for split, payload in quality_cache.items():
			headers, rows, summary = payload
			path = _work_path(sid, job_id, split)
			_write_csv(path, headers, rows)
			previews[split] = {"headers": headers, "rows": rows[:10], "total": len(rows)}
			summaries[split] = summary
			label_stats[split] = _label_counts(rows, meta["label_col"])

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
		"label_stats": label_stats,
		"log_lines": log_lines,
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
