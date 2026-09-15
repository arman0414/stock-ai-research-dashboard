from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from stock_ai.features.dataset import BASE_PRICE_COLUMNS, TARGET_COLUMN_PREFIXES


EXCLUDED_FEATURE_COLUMNS = set(BASE_PRICE_COLUMNS) | {"source", "fetched_at"}


@dataclass
class FeaturePreprocessor:
    feature_columns: list[str]
    pipeline: Pipeline

    def transform(self, dataset: pd.DataFrame) -> pd.DataFrame:
        values = _clean_numeric(dataset[self.feature_columns])
        transformed = self.pipeline.transform(values)
        return pd.DataFrame(transformed, columns=self.feature_columns, index=dataset.index)


def select_model_feature_columns(dataset: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in dataset.columns:
        if column in EXCLUDED_FEATURE_COLUMNS:
            continue
        if column.startswith(TARGET_COLUMN_PREFIXES) or column.startswith("future_"):
            continue
        if pd.api.types.is_numeric_dtype(dataset[column]):
            columns.append(column)
    return columns


def fit_preprocessor(train_dataset: pd.DataFrame, feature_columns: list[str] | None = None, scale: bool = True) -> FeaturePreprocessor:
    selected_columns = feature_columns or select_model_feature_columns(train_dataset)
    selected_columns = [
        column
        for column in selected_columns
        if _clean_numeric(train_dataset[[column]])[column].notna().any()
    ]
    if not selected_columns:
        raise ValueError("No numeric model feature columns found")

    steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scaler", StandardScaler()))

    pipeline = Pipeline(steps)
    pipeline.fit(_clean_numeric(train_dataset[selected_columns]))
    return FeaturePreprocessor(feature_columns=selected_columns, pipeline=pipeline)


def transform_with_preprocessor(preprocessor: FeaturePreprocessor, dataset: pd.DataFrame) -> pd.DataFrame:
    return preprocessor.transform(dataset)


def _clean_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
