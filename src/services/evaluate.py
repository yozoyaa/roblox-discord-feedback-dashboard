from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd
from sklearn.metrics import (
	accuracy_score,
	classification_report,
	confusion_matrix,
	precision_score,
	recall_score,
)

from src.utils.sharedutilities import ensure_dir, now_log_time, now_stamp

ALLOWED_LABELS = {"negatif", "positif"}
LABEL_ORDER = ["negatif", "positif"]


def _norm_label(v: Any) -> str:
	return str(v or "").strip().lower()


def _count_binary(labels: List[str]) -> Dict[str, int]:
	return {
		"negatif": sum(1 for l in labels if l == "negatif"),
		"positif": sum(1 for l in labels if l == "positif"),
	}


def _ensure_dir(sid: str) -> Path:
	root = Path(__file__).resolve().parents[2]
	out_dir = root / "data" / "sessions" / sid / "outputs" / "evaluate"
	ensure_dir(out_dir)
	return out_dir


def _preview_rows(df: pd.DataFrame, limit: int = 20) -> List[Dict[str, Any]]:
	return df.head(limit).to_dict(orient="records")


def evaluate_model(
	sid: str,
	artifact_path: str,
	data_path: str,
	prefix: str,
	text_col_override: Optional[str] = None,
	label_col_override: Optional[str] = None,
	raw_path: Optional[str] = None,
	pre_train_path: Optional[str] = None,
	pre_test_path: Optional[str] = None,
	pre_val_path: Optional[str] = None,
) -> Dict[str, Any]:
	artifact = joblib.load(artifact_path)
	if not isinstance(artifact, dict) or "pipeline" not in artifact:
		raise ValueError("Artifact tidak valid.")

	pipeline = artifact["pipeline"]
	artifact_text_col = artifact.get("text_col", "tokens_stemmed")
	artifact_label_col = artifact.get("label_col", "sentimen")
	text_col = text_col_override.strip() if text_col_override else artifact_text_col
	label_col = label_col_override.strip() if label_col_override else artifact_label_col

	df = pd.read_csv(data_path)
	if text_col not in df.columns:
		raise ValueError(f"TEXT_COL '{text_col}' tidak ditemukan di data uji.")

	labels_artifact = artifact.get("labels")
	if labels_artifact is None and hasattr(pipeline, "classes_"):
		labels_artifact = list(pipeline.classes_)
	if labels_artifact:
		labels_artifact_norm = {_norm_label(l) for l in labels_artifact}
		invalid_art = labels_artifact_norm - ALLOWED_LABELS
		if invalid_art:
			raise ValueError(f"Label model tidak valid: {sorted(invalid_art)}. Model harus binary: negatif/positif.")
		missing = ALLOWED_LABELS - labels_artifact_norm
		if missing:
			raise ValueError(f"Model harus punya kedua label: negatif dan positif. Saat ini: {sorted(labels_artifact_norm)}")
	labels_sorted = LABEL_ORDER if labels_artifact else None

	X_raw = df[text_col].fillna("").astype(str)
	mask_nonempty = X_raw.str.strip() != ""
	rows_dropped = int((~mask_nonempty).sum())
	df_eval = df.loc[mask_nonempty].copy()
	X = df_eval[text_col].fillna("").astype(str)

	if len(df_eval) == 0:
		raise ValueError("Semua baris kosong setelah cleaning teks.")

	def _safe_count_rows(csv_path: Optional[str]) -> tuple[int, Optional[str]]:
		if not csv_path:
			return 0, None
		try:
			df_tmp = pd.read_csv(csv_path)
			return len(df_tmp), None
		except Exception as e:
			return 0, f"Gagal membaca {Path(csv_path).name}: {e}"

	total_raw_data, warn_raw = _safe_count_rows(raw_path)
	total_pre_train, warn_pre_train = _safe_count_rows(pre_train_path)
	total_pre_test, warn_pre_test = _safe_count_rows(pre_test_path)
	total_pre_val, warn_pre_val = _safe_count_rows(pre_val_path)
	total_preprocessed_data = total_pre_train + total_pre_test + total_pre_val
	optional_warnings = [w for w in [warn_raw, warn_pre_train, warn_pre_test, warn_pre_val] if w]

	y_pred = pipeline.predict(X)
	y_pred_norm = [_norm_label(v) for v in y_pred]
	extra_pred = set(y_pred_norm) - ALLOWED_LABELS
	if extra_pred:
		raise ValueError(f"Prediksi model mengandung label di luar negatif/positif: {sorted(extra_pred)}")
	conf = None
	if hasattr(pipeline, "predict_proba"):
		try:
			probs = pipeline.predict_proba(X)
			conf = probs.max(axis=1)
		except Exception:
			probs = None
	else:
		probs = None

	df_classified = pd.DataFrame()
	df_classified[text_col] = X
	df_classified["predicted_label"] = y_pred_norm
	if conf is not None:
		df_classified["confidence"] = conf

	metrics = {
		"accuracy": None,
		"precision": {"per_label": {}, "macro": None, "weighted": None},
		"recall": {"per_label": {}, "macro": None, "weighted": None},
		"confusion_matrix": None,
		"classification_report": None,
	}
	mode = "classification_only"
	true_label_counts: Dict[str, int] = {}
	pred_label_counts: Dict[str, int] = _count_binary(df_classified["predicted_label"].tolist())

	if label_col in df_eval.columns:
		y_true = df_eval[label_col].fillna("").astype(str).map(_norm_label)
		extra_true = set(y_true.unique().tolist()) - ALLOWED_LABELS
		if extra_true:
			raise ValueError(f"Label di Data Uji tidak valid: {sorted(extra_true)}. Hanya mendukung: negatif/positif.")
		if labels_sorted is None:
			labels_sorted = LABEL_ORDER
		missing_model = set(y_true.unique().tolist()) - set(labels_sorted)
		if missing_model:
			raise ValueError(f"Label di Data Uji tidak ada di model: {sorted(missing_model)}")

		metrics["accuracy"] = float(accuracy_score(y_true, y_pred_norm))
		metrics["precision"]["macro"] = float(precision_score(y_true, y_pred_norm, average="macro", zero_division=0))
		metrics["precision"]["weighted"] = float(precision_score(y_true, y_pred_norm, average="weighted", zero_division=0))
		metrics["recall"]["macro"] = float(recall_score(y_true, y_pred_norm, average="macro", zero_division=0))
		metrics["recall"]["weighted"] = float(recall_score(y_true, y_pred_norm, average="weighted", zero_division=0))
		metrics["confusion_matrix"] = confusion_matrix(y_true, y_pred_norm, labels=LABEL_ORDER).tolist()
		report = classification_report(y_true, y_pred_norm, labels=LABEL_ORDER, output_dict=True, zero_division=0)
		metrics["classification_report"] = report
		for lbl in LABEL_ORDER:
			if lbl in report:
				metrics["precision"]["per_label"][lbl] = float(report[lbl].get("precision", 0.0))
				metrics["recall"]["per_label"][lbl] = float(report[lbl].get("recall", 0.0))
		mode = "with_ground_truth"
		true_label_counts = _count_binary(y_true.tolist())

	# Save outputs
	out_dir = _ensure_dir(sid)
	stamp = now_stamp()
	summary_name = f"{prefix}_Evaluate_Summary_{stamp}.json"
	classified_name = f"{prefix}_Classified_{stamp}.csv"

	summary_payload = {
		"created_at": now_log_time(),
		"mode": mode,
		"artifact_info": {
			"text_col": text_col,
			"label_col": label_col,
			"labels": labels_sorted,
			"params": artifact.get("params") or artifact.get("best_params") or artifact.get("config_used"),
		},
		"stats": {
			"total_rows_uploaded": int(len(df)),
			"rows_dropped_empty_text": rows_dropped,
			"total_classified": int(len(df_classified)),
			"total_train": artifact.get("dataset_summary", {}).get("counts", {}).get("train"),
			"total_test": artifact.get("dataset_summary", {}).get("counts", {}).get("test"),
			"total_val": artifact.get("dataset_summary", {}).get("counts", {}).get("val"),
			"true_label_counts": true_label_counts,
			"pred_label_counts": pred_label_counts,
			"total_raw_data": total_raw_data,
			"total_preprocessed_train": total_pre_train,
			"total_preprocessed_test": total_pre_test,
			"total_preprocessed_val": total_pre_val,
			"total_preprocessed_data": total_preprocessed_data,
		},
		"optional_warnings": optional_warnings,
		"metrics": metrics,
	}

	(out_dir / summary_name).write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
	df_classified.to_csv(out_dir / classified_name, index=False, encoding="utf-8")

	zip_name = f"{prefix}_Evaluate_{stamp}_{sid}.zip"
	with zipfile.ZipFile(out_dir / zip_name, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		zf.write(out_dir / summary_name, arcname=summary_name)
		zf.write(out_dir / classified_name, arcname=classified_name)
		if metrics["confusion_matrix"] is not None:
			cm_csv = out_dir / f"{prefix}_Confusion_{stamp}.csv"
			pd.DataFrame(metrics["confusion_matrix"]).to_csv(cm_csv, index=False, header=False, encoding="utf-8")
			zf.write(cm_csv, arcname=cm_csv.name)
			cm_csv.unlink(missing_ok=True)

	return {
		"ok": True,
		"created_at": summary_payload["created_at"],
		"mode": mode,
		"labels": labels_sorted or [],
		"stats": summary_payload["stats"],
		"metrics": metrics,
		"preview_classified": _preview_rows(df_classified),
		"summary_file": summary_name,
		"classified_file": classified_name,
		"zip_file": zip_name,
	}
