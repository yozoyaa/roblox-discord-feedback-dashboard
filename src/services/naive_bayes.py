from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
	accuracy_score,
	classification_report,
	confusion_matrix,
	f1_score,
)
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.utils.class_weight import compute_sample_weight

from src.utils.sharedutilities import ensure_dir, now_log_time, now_stamp

ALLOWED_LABELS = {"negatif", "positif"}


@dataclass(frozen=True)
class NBConfig:
	text_col: str = "tokens_stemmed"
	label_col: str = "sentimen"
	min_df: int = 2
	max_df: float = 0.8
	norm: str = "l2"
	sublinear_tf: bool = True
	max_features: int = 5000
	ngram_range: Tuple[int, int] = (1, 2)
	alpha: float = 1.0
	alpha_list: List[float] = None
	fit_prior: bool = True
	use_balanced_sample_weight: bool = True
	retrain_on_train_plus_val: bool = True


def _norm_label(v: Any) -> str:
	return str(v or "").strip().lower()


def _load_xy(csv_path: Path, *, text_col: str, label_col: str) -> Tuple[pd.Series, pd.Series, pd.DataFrame]:
	df = pd.read_csv(csv_path)
	if text_col not in df.columns:
		raise ValueError(f"TEXT_COL '{text_col}' tidak ditemukan di {csv_path.name}")
	if label_col not in df.columns:
		raise ValueError(f"LABEL_COL '{label_col}' tidak ditemukan di {csv_path.name}")
	x = df[text_col].fillna("").astype(str)
	y = df[label_col].fillna("").astype(str).map(_norm_label)
	return x, y, df


def _label_dist(y: pd.Series) -> Dict[str, Dict[str, float]]:
	cnt = y.value_counts()
	total = cnt.sum() if cnt.sum() > 0 else 1
	out: Dict[str, Dict[str, float]] = {}
	for lbl in ["negatif", "positif"]:
		v = int(cnt.get(lbl, 0))
		out[lbl] = {"count": v, "pct": float(v) / float(total)}
	return out


def _build_pipeline(config: NBConfig, max_features: int, ngram_range: Tuple[int, int], alpha: float) -> Pipeline:
	return Pipeline(
		steps=[
			(
				"tfidf",
				TfidfVectorizer(
					max_features=max_features,
					min_df=config.min_df,
					max_df=config.max_df,
					ngram_range=ngram_range,
					norm=config.norm,
					sublinear_tf=config.sublinear_tf,
				),
			),
			(
				"nb",
				MultinomialNB(
					alpha=alpha,
					fit_prior=config.fit_prior,
				),
			),
		]
	)


def _top_terms(pipe: Pipeline, labels: List[str], top_n: int = 20) -> Dict[str, List[Dict[str, Any]]]:
	out: Dict[str, List[Dict[str, Any]]] = {}
	vectorizer: TfidfVectorizer = pipe.named_steps["tfidf"]
	nb: MultinomialNB = pipe.named_steps["nb"]
	feature_names = vectorizer.get_feature_names_out()
	for idx, label in enumerate(labels):
		log_probs = nb.feature_log_prob_[idx]
		top_idx = log_probs.argsort()[::-1][:top_n]
		out[label] = [{"term": feature_names[i], "score": float(log_probs[i])} for i in top_idx]
	return out


def _misclassified_examples(
	pipe: Pipeline, X: pd.Series, y_true: pd.Series, max_examples: int = 20
) -> List[Dict[str, Any]]:
	preds = pipe.predict(X)
	probs = pipe.predict_proba(X)
	out: List[Dict[str, Any]] = []
	for i, (pred, true) in enumerate(zip(preds, y_true)):
		if pred != true:
			conf = float(probs[i].max()) if probs is not None else 0.0
			out.append(
				{
					"text": str(X.iloc[i])[:500],
					"y_true": str(true),
					"y_pred": str(pred),
					"confidence": conf,
					"probs": {str(lbl): float(p) for lbl, p in zip(pipe.classes_, probs[i])} if probs is not None else {},
				}
			)
			if len(out) >= max_examples:
				break
	return out


def _full_predictions_df(pipe: Pipeline, df: pd.DataFrame, text_col: str, y_true: pd.Series) -> pd.DataFrame:
	x_series = df[text_col].fillna("").astype(str)
	y_pred = pipe.predict(x_series)
	conf = None
	probs = None
	if hasattr(pipe, "predict_proba"):
		try:
			probs = pipe.predict_proba(x_series)
			conf = probs.max(axis=1)
		except Exception:
			probs = None

	records = []
	for i, (txt, yt, yp) in enumerate(zip(x_series, y_true, y_pred)):
		row = {
			text_col: txt,
			"y_true": yt,
			"y_pred": yp,
			"correct": bool(yp == yt),
		}
		if conf is not None:
			row["confidence"] = float(conf[i])
		if probs is not None:
			row["probs"] = json.dumps({str(lbl): float(p) for lbl, p in zip(pipe.classes_, probs[i])})
		records.append(row)
	return pd.DataFrame(records)


def _confusion_and_report(y_true: pd.Series, y_pred: pd.Series, labels_sorted: List[str]) -> Dict[str, Any]:
	return {
		"accuracy": float(accuracy_score(y_true, y_pred)),
		"macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
		"weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
		"report": classification_report(
			y_true,
			y_pred,
			digits=4,
			zero_division=0,
			output_dict=True,
		),
		"confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels_sorted).tolist(),
	}


def _save_artifact(sid: str, prefix: str, payload: Dict[str, Any]) -> Dict[str, str]:
	out_dir = Path(__file__).resolve().parents[2] / "data" / "sessions" / sid / "outputs" / "naive_bayes"
	ensure_dir(out_dir)
	stamp = now_stamp()
	temp_dir = out_dir / f"tmp_{stamp}"
	ensure_dir(temp_dir)

	file_map: Dict[str, str] = {}

	joblib.dump(payload["artifact"], temp_dir / "naive_bayes_artifact.joblib")
	file_map["model_joblib"] = "naive_bayes_artifact.joblib"

	(temp_dir / "metrics.json").write_text(json.dumps(payload["metrics"], ensure_ascii=False, indent=2), encoding="utf-8")
	file_map["metrics_json"] = "metrics.json"

	(temp_dir / "confusion_matrix.json").write_text(
		json.dumps(payload["metrics"]["results"]["test"]["confusion_matrix"], ensure_ascii=False, indent=2), encoding="utf-8"
	)
	file_map["confusion_json"] = "confusion_matrix.json"

	for name, df in (payload.get("files") or {}).items():
		if isinstance(df, pd.DataFrame):
			df.to_csv(temp_dir / name, index=False, encoding="utf-8")
			file_map[name] = name

	if payload.get("misclassified_sample"):
		pd.DataFrame(payload["misclassified_sample"]).to_csv(temp_dir / "misclassified_sample.csv", index=False, encoding="utf-8")
		file_map["misclassified_sample"] = "misclassified_sample.csv"

	zip_name = f"{prefix}_{stamp}_{sid}.zip"
	with zipfile.ZipFile(out_dir / zip_name, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		for p in temp_dir.iterdir():
			zf.write(p, arcname=p.name)

	for p in temp_dir.iterdir():
		p.unlink(missing_ok=True)
	temp_dir.rmdir()
	file_map["zip"] = zip_name
	return file_map


def train_naive_bayes(
	sid: str,
	train_path: str,
	test_path: str,
	val_path: Optional[str],
	config: NBConfig,
	prefix: str = "naive_bayes",
) -> Dict[str, Any]:
	train_path_p = Path(train_path)
	test_path_p = Path(test_path)
	val_path_p = Path(val_path) if val_path else None

	X_train, y_train, df_train = _load_xy(train_path_p, text_col=config.text_col, label_col=config.label_col)
	X_test, y_test, df_test = _load_xy(test_path_p, text_col=config.text_col, label_col=config.label_col)
	mode = "3way" if val_path_p else "2way"
	if mode == "3way":
		X_val, y_val, df_val = _load_xy(val_path_p, text_col=config.text_col, label_col=config.label_col)
	else:
		X_val, y_val, df_val = None, None, None

	# Schema consistency
	cols_base = set(df_train.columns)
	for df in [df_test, df_val] if df_val is not None else [df_test]:
		if df is not None and set(df.columns) != cols_base:
			raise ValueError("Schema tidak konsisten antar file (kolom/header harus sama).")

	# Label subset
	train_labels_unique = set(y_train.unique().tolist())
	invalid_train = train_labels_unique - ALLOWED_LABELS
	if invalid_train:
		raise ValueError(f"Label tidak valid di Train: {sorted(invalid_train)}. Hanya mendukung: negatif/positif.")
	missing = ALLOWED_LABELS - train_labels_unique
	if missing:
		raise ValueError(
			f"Train harus punya kedua label (negatif dan positif). Missing: {sorted(missing)}. Saat ini: {sorted(train_labels_unique)}"
		)
	for name, y_split in [("Test", y_test), ("Val", y_val)]:
		if y_split is not None:
			split_unique = set(y_split.unique().tolist())
			invalid_split = split_unique - ALLOWED_LABELS
			if invalid_split:
				raise ValueError(f"Label tidak valid di {name}: {sorted(invalid_split)}. Hanya mendukung: negatif/positif.")
			extra = split_unique - train_labels_unique
			if extra:
				raise ValueError(f"Label di {name} tidak ada di Train: {sorted(extra)}")

	# Train size rule
	if mode == "3way":
		if len(df_train) <= (len(df_test) + len(df_val or [])):
			raise ValueError("Train harus lebih besar dari (Test + Val).")
	else:
		if len(df_train) <= len(df_test):
			raise ValueError("Train harus lebih besar dari Test.")

	dataset_summary = {
		"counts": {"train": len(df_train), "test": len(df_test), "val": len(df_val) if df_val is not None else 0},
		"label_dist": {
			"train": _label_dist(y_train),
			"test": _label_dist(y_test),
			"val": _label_dist(y_val) if y_val is not None else {},
		},
		"warnings": [],
	}
	for lbl in ["negatif", "positif"]:
		stats = dataset_summary["label_dist"]["train"].get(lbl, {"count": 0})
		if stats.get("count", 0) < 20:
			dataset_summary["warnings"].append(f"Label '{lbl}' kurang dari 20 data di Train.")
	neg_count = dataset_summary["label_dist"]["train"].get("negatif", {}).get("count", 0)
	pos_count = dataset_summary["label_dist"]["train"].get("positif", {}).get("count", 0)
	total_train = max(neg_count + pos_count, 1)
	min_pct = min(neg_count, pos_count) / total_train * 100
	if min_pct < 10:
		dataset_summary["warnings"].append(
			f"Train sangat tidak seimbang: negatif={neg_count}, positif={pos_count}. Pertimbangkan tambah data/penyeimbangan."
		)

	labels_sorted = ["negatif", "positif"]
	search_alphas = config.alpha_list if config.alpha_list else [config.alpha]
	search_space = [(config.max_features, config.ngram_range, a) for a in search_alphas]

	best_pipe = None
	best_params = None
	best_val_macro = -1.0

	def fit_pipeline(max_features: int, ngram_range: Tuple[int, int], alpha: float, x_fit, y_fit):
		pipe = _build_pipeline(config, max_features, ngram_range, alpha)
		fit_kwargs: Dict[str, Any] = {}
		if config.use_balanced_sample_weight:
			fit_kwargs["nb__sample_weight"] = compute_sample_weight(class_weight="balanced", y=y_fit)
		pipe.fit(x_fit, y_fit, **fit_kwargs)
		return pipe

	if mode == "3way":
		for max_feat, ng_range, alpha in search_space:
			cand_pipe = fit_pipeline(max_feat, ng_range, alpha, X_train, y_train)
			val_pred = cand_pipe.predict(X_val)
			val_macro = float(f1_score(y_val, val_pred, average="macro", zero_division=0))
			if val_macro > best_val_macro:
				best_val_macro = val_macro
				best_pipe = cand_pipe
				best_params = {
					"alpha": alpha,
					"ngram_range": ng_range,
					"max_features": max_feat,
					"min_df": config.min_df,
					"max_df": config.max_df,
					"norm": config.norm,
					"sublinear_tf": config.sublinear_tf,
					"fit_prior": config.fit_prior,
					"use_balanced_sample_weight": config.use_balanced_sample_weight,
					"retrain_on_train_plus_val": config.retrain_on_train_plus_val,
				}

		if best_pipe is None:
			raise RuntimeError("Tidak ada kandidat model yang dilatih.")

		if config.retrain_on_train_plus_val:
			X_tr = pd.concat([X_train, X_val], ignore_index=True)
			y_tr = pd.concat([y_train, y_val], ignore_index=True)
			best_pipe = fit_pipeline(best_params["max_features"], tuple(best_params["ngram_range"]), best_params["alpha"], X_tr, y_tr)
	else:
		best_pipe = fit_pipeline(config.max_features, config.ngram_range, config.alpha, X_train, y_train)
		best_params = {
			"alpha": config.alpha,
			"ngram_range": config.ngram_range,
			"max_features": config.max_features,
			"min_df": config.min_df,
			"max_df": config.max_df,
			"norm": config.norm,
			"sublinear_tf": config.sublinear_tf,
			"fit_prior": config.fit_prior,
			"use_balanced_sample_weight": config.use_balanced_sample_weight,
			"retrain_on_train_plus_val": False,
		}

	# Evaluate
	test_pred = best_pipe.predict(X_test)
	results: Dict[str, Any] = {
		"test": _confusion_and_report(y_test, test_pred, labels_sorted),
	}
	if mode == "3way":
		results["best_val_macro_f1"] = best_val_macro
		results["best_params"] = best_params

	# Misclassified and top terms
	misclassified = _misclassified_examples(best_pipe, X_test, y_test, max_examples=20)
	results["misclassified"] = misclassified
	results["top_terms"] = _top_terms(best_pipe, labels_sorted, top_n=20)

	# Full prediction exports
	full_files: Dict[str, pd.DataFrame] = {}
	full_files["test_predictions_full.csv"] = _full_predictions_df(best_pipe, df_test, config.text_col, y_test)
	if mode == "3way" and df_val is not None and y_val is not None:
		full_files["val_predictions_full.csv"] = _full_predictions_df(best_pipe, df_val, config.text_col, y_val)

	payload = {
		"ok": True,
		"mode": mode,
		"created_at": now_log_time(),
		"config_used": best_params,
		"dataset_summary": dataset_summary,
		"results": results,
		"labels": labels_sorted,
	}

	artifact_payload = {
		"artifact": {
			"pipeline": best_pipe,
			"text_col": config.text_col,
			"label_col": config.label_col,
			"params": best_params,
			"dataset_summary": dataset_summary,
			"results": results,
		},
		"metrics": payload,
		"files": full_files,
		"misclassified_sample": misclassified[:20],
	}
	file_map = _save_artifact(sid, prefix, artifact_payload)
	payload["artifacts"] = {
		"zip": file_map.get("zip", ""),
		"model_joblib": file_map.get("model_joblib"),
		"metrics_json": file_map.get("metrics_json"),
		"confusion_json": file_map.get("confusion_json"),
		"test_predictions_full": file_map.get("test_predictions_full.csv"),
		"val_predictions_full": file_map.get("val_predictions_full.csv"),
		"misclassified_sample": file_map.get("misclassified_sample"),
	}
	payload["artifact"] = payload["artifacts"]["zip"]
	return payload
