from __future__ import annotations

import csv
import io
import math
import random
from pathlib import Path
from typing import List, Tuple, Dict

from src.utils.sharedutilities import ensure_dir, now_stamp


def read_csv_text(text: str) -> Tuple[List[str], List[List[str]]]:
	reader = csv.reader(io.StringIO(text))
	rows = list(reader)
	if not rows:
		return [], []
	return rows[0], rows[1:]


def to_csv_string(headers: List[str], rows: List[List[str]]) -> str:
	out = io.StringIO()
	writer = csv.writer(out, lineterminator="\n")
	writer.writerow(headers)
	for r in rows:
		writer.writerow(r)
	return out.getvalue()


def split_rows(
	rows: List[List[str]],
	percents: List[int],
	*,
	shuffle: bool = True,
	seed: int = 42,
) -> List[List[List[str]]]:
	total = len(rows)
	if total == 0:
		return [[] for _ in percents]
	
	rows_copy = list(rows)

	if shuffle:
		rng = random.Random(seed)
		rng.shuffle(rows_copy)

	counts = []
	used = 0
	for p in percents[:-1]:
		c = int(math.floor(total * (p / 100.0)))
		counts.append(c)
		used += c
	counts.append(total - used)

	result = []
	start = 0
	for c in counts:
		end = start + c
		result.append(rows_copy[start:end])
		start = end

	return result


def split_rows_stratified(
	rows: List[List[str]],
	percents: List[int],
	*,
	label_index: int,
	seed: int = 42,
	shuffle_within_splits: bool = True,
) -> List[List[List[str]]]:
	total = len(rows)
	if total == 0:
		return [[] for _ in percents]

	buckets: Dict[str, List[List[str]]] = {}
	for r in rows:
		if label_index >= len(r):
			continue
		label = r[label_index]
		buckets.setdefault(label, []).append(r)

	rng = random.Random(seed)

	splits: List[List[List[str]]] = [[] for _ in percents]

	for _, bucket_rows in buckets.items():
		rng.shuffle(bucket_rows)

		n = len(bucket_rows)
		counts = []
		used = 0
		for p in percents[:-1]:
			c = int(math.floor(n * (p / 100.0)))
			counts.append(c)
			used += c
		counts.append(n - used)

		start = 0
		for i, c in enumerate(counts):
			end = start + c
			splits[i].extend(bucket_rows[start:end])
			start = end

	if shuffle_within_splits:
		for s in splits:
			rng.shuffle(s)

	return splits


def make_previews(headers: List[str], splits: List[Tuple[str, List[List[str]]]]) -> List[Dict]:
	previews = []
	for name, rows in splits:
		previews.append(
			{
				"name": name,
				"headers": headers,
				"rows": rows[:10],
				"total": len(rows),
			}
		)
	return previews


def save_split_files(out_dir: Path, prefix: str, sid: str, payload: List[Dict[str, str]]) -> str:
	ensure_dir(out_dir)
	ts = now_stamp()
	csv_files = []
	for item in payload:
		name = item.get("name") or "data"
		text = item.get("csv") or ""
		if not text:
			continue
		filename = f"{prefix}_{name}_{ts}_{sid}.csv"
		(out_dir / filename).write_text(text, encoding="utf-8")
		csv_files.append(filename)

	if not csv_files:
		raise RuntimeError("Tidak ada file untuk disimpan.")

	zip_name = f"{prefix}_{ts}_{sid}.zip"
	zip_path = out_dir / zip_name
	import zipfile

	with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		for fn in csv_files:
			zf.write(out_dir / fn, arcname=fn)

	return zip_name
