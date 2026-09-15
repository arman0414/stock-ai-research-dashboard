from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    mean_absolute_error,
    root_mean_squared_error,
    precision_recall_fscore_support,
    precision_score,
    r2_score,
    recall_score,
)

from stock_ai.ml.config import CLASS_LABELS


CONFIDENCE_THRESHOLDS = (0.50, 0.60, 0.70, 0.80)


@dataclass(frozen=True)
class ModelSelectionResult:
    best_model_name: str
    validation_metric_name: str
    validation_metric_value: float
    used_test_set: bool = False


def classification_metrics(
    y_true: pd.Series | np.ndarray,
    y_pred: pd.Series | np.ndarray,
    probabilities: np.ndarray | None = None,
    labels: list[str] | None = None,
) -> dict:
    labels = labels or CLASS_LABELS
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true_arr,
        y_pred_arr,
        labels=labels,
        zero_division=0,
    )
    metrics = {
        "accuracy": float(accuracy_score(y_true_arr, y_pred_arr)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true_arr, y_pred_arr)),
        "macro_precision": float(precision_score(y_true_arr, y_pred_arr, labels=labels, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true_arr, y_pred_arr, labels=labels, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_true_arr, y_pred_arr, labels=labels, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true_arr, y_pred_arr, labels=labels).tolist(),
        "class_metrics": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(labels)
        },
    }

    if probabilities is not None:
        metrics["log_loss"] = float(log_loss(y_true_arr, probabilities, labels=labels))
        metrics["brier_score_multiclass"] = float(multiclass_brier_score(y_true_arr, probabilities, labels))
        metrics["confidence"] = confidence_threshold_metrics(y_true_arr, y_pred_arr, probabilities, labels)

    return metrics


def regression_metrics(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray) -> dict[str, float]:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        "rmse": float(root_mean_squared_error(y_true_arr, y_pred_arr)),
        "r2": float(r2_score(y_true_arr, y_pred_arr)),
        "direction_accuracy": float((np.sign(y_true_arr) == np.sign(y_pred_arr)).mean()),
    }


def confidence_threshold_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
    labels: list[str] | None = None,
    thresholds: tuple[float, ...] = CONFIDENCE_THRESHOLDS,
) -> dict[str, dict[str, float | int]]:
    labels = labels or CLASS_LABELS
    max_probabilities = probabilities.max(axis=1)
    total = len(y_true)
    results: dict[str, dict[str, float | int]] = {}

    for threshold in thresholds:
        mask = max_probabilities >= threshold
        key = f">={threshold:.2f}"
        if not mask.any():
            results[key] = {
                "count": 0,
                "coverage": 0.0,
                "accuracy": np.nan,
                "balanced_accuracy": np.nan,
                "up_precision": np.nan,
                "down_precision": np.nan,
            }
            continue

        subset_true = y_true[mask]
        subset_pred = y_pred[mask]
        results[key] = {
            "count": int(mask.sum()),
            "coverage": float(mask.sum() / total),
            "accuracy": float(accuracy_score(subset_true, subset_pred)),
            "balanced_accuracy": float(balanced_accuracy_score(subset_true, subset_pred)),
            "up_precision": _class_precision(subset_true, subset_pred, "UP"),
            "down_precision": _class_precision(subset_true, subset_pred, "DOWN"),
        }

    return results


def multiclass_brier_score(y_true: np.ndarray, probabilities: np.ndarray, labels: list[str] | None = None) -> float:
    labels = labels or CLASS_LABELS
    label_to_index = {label: index for index, label in enumerate(labels)}
    encoded = np.zeros_like(probabilities, dtype=float)
    for row_index, label in enumerate(y_true):
        encoded[row_index, label_to_index[str(label)]] = 1.0
    return float(np.mean(np.sum((probabilities - encoded) ** 2, axis=1)))


def class_distribution(labels: pd.Series | np.ndarray) -> dict[str, dict[str, float | int]]:
    values = pd.Series(labels).value_counts(dropna=False)
    total = len(labels)
    return {
        label: {
            "count": int(values.get(label, 0)),
            "percentage": float(values.get(label, 0) / total) if total else 0.0,
        }
        for label in CLASS_LABELS
    }


def select_best_model(validation_results: dict[str, dict], metric_name: str, greater_is_better: bool = True) -> ModelSelectionResult:
    if not validation_results:
        raise ValueError("No validation results were provided")

    def score(item: tuple[str, dict]) -> float:
        value = item[1].get(metric_name)
        if value is None:
            raise ValueError(f"Validation result missing metric: {metric_name}")
        return float(value)

    best_name, best_metrics = max(validation_results.items(), key=score) if greater_is_better else min(validation_results.items(), key=score)
    return ModelSelectionResult(
        best_model_name=best_name,
        validation_metric_name=metric_name,
        validation_metric_value=float(best_metrics[metric_name]),
        used_test_set=False,
    )


def _class_precision(y_true: np.ndarray, y_pred: np.ndarray, class_label: str) -> float:
    return float(precision_score(y_true, y_pred, labels=[class_label], average="micro", zero_division=0))
