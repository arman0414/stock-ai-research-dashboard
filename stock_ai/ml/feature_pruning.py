from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FeaturePruningReport:
    original_feature_count: int
    kept_feature_count: int
    constant_features: list[str]
    near_constant_features: list[str]
    duplicate_features: list[str]
    sparse_features: list[str]
    highly_correlated_pairs: list[dict[str, float | str]]

    @property
    def removed_feature_count(self) -> int:
        return self.original_feature_count - self.kept_feature_count


def diagnose_features(
    frame: pd.DataFrame,
    feature_columns: list[str],
    near_constant_threshold: float = 0.995,
    sparse_threshold: float = 0.98,
    correlation_threshold: float = 0.98,
) -> dict:
    numeric = frame[feature_columns].apply(pd.to_numeric, errors="coerce")
    non_missing_ratio = numeric.notna().mean()
    unique_counts = numeric.nunique(dropna=True)
    constant = sorted(unique_counts[unique_counts <= 1].index.tolist())
    sparse = sorted(non_missing_ratio[non_missing_ratio <= (1 - sparse_threshold)].index.tolist())
    near_constant = []
    for column in numeric.columns:
        values = numeric[column].dropna()
        if values.empty or column in constant:
            continue
        top_ratio = values.value_counts(normalize=True).iloc[0]
        if top_ratio >= near_constant_threshold:
            near_constant.append(column)
    duplicate = sorted(numeric.T.duplicated().loc[lambda s: s].index.tolist())
    correlated = _highly_correlated_pairs(numeric, correlation_threshold=correlation_threshold)
    return {
        "feature_count": len(feature_columns),
        "constant_features": constant,
        "near_constant_features": sorted(near_constant),
        "duplicate_features": duplicate,
        "sparse_features": sparse,
        "highly_correlated_pairs": correlated,
    }


def prune_features(
    train_frame: pd.DataFrame,
    feature_columns: list[str],
    remove_constant: bool = True,
    remove_duplicate: bool = True,
    remove_sparse: bool = True,
    sparse_threshold: float = 0.98,
) -> tuple[list[str], FeaturePruningReport]:
    diagnostics = diagnose_features(train_frame, feature_columns, sparse_threshold=sparse_threshold)
    remove: set[str] = set()
    if remove_constant:
        remove.update(diagnostics["constant_features"])
    if remove_duplicate:
        remove.update(diagnostics["duplicate_features"])
    if remove_sparse:
        remove.update(diagnostics["sparse_features"])

    kept = [column for column in feature_columns if column not in remove]
    report = FeaturePruningReport(
        original_feature_count=len(feature_columns),
        kept_feature_count=len(kept),
        constant_features=diagnostics["constant_features"],
        near_constant_features=diagnostics["near_constant_features"],
        duplicate_features=diagnostics["duplicate_features"],
        sparse_features=diagnostics["sparse_features"],
        highly_correlated_pairs=diagnostics["highly_correlated_pairs"],
    )
    return kept, report


def _highly_correlated_pairs(frame: pd.DataFrame, correlation_threshold: float) -> list[dict[str, float | str]]:
    usable = frame.dropna(axis=1, how="all")
    if usable.shape[1] < 2:
        return []
    corr = usable.corr(numeric_only=True).abs()
    pairs = []
    columns = list(corr.columns)
    for left_index, left in enumerate(columns):
        for right in columns[left_index + 1 :]:
            value = corr.at[left, right]
            if pd.notna(value) and value >= correlation_threshold:
                pairs.append({"left": left, "right": right, "correlation": float(value)})
    return sorted(pairs, key=lambda item: item["correlation"], reverse=True)

