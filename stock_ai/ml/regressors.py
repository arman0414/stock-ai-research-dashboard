from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

from stock_ai.ml.config import ModelConfig
from stock_ai.ml.preprocessing import FeaturePreprocessor


try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover
    XGBRegressor = None


@dataclass
class FittedRegressor:
    name: str
    model: object
    preprocessor: FeaturePreprocessor
    feature_columns: list[str]

    def predict(self, dataset: pd.DataFrame) -> np.ndarray:
        X = self.preprocessor.transform(dataset)
        return np.asarray(self.model.predict(X), dtype=float)


def create_regressor(name: str, config: ModelConfig | None = None):
    config = config or ModelConfig()
    normalized = name.lower()

    if normalized == "dummy":
        return DummyRegressor(strategy="mean")
    if normalized in {"ridge", "linear"}:
        return Ridge(alpha=1.0, random_state=config.random_state)
    if normalized == "random_forest":
        return RandomForestRegressor(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=3,
            random_state=config.random_state,
            n_jobs=1,
        )
    if normalized == "xgboost":
        if XGBRegressor is None:
            raise ImportError("xgboost is not installed. Install xgboost to train XGBoost regressors.")
        xgb = config.xgboost
        return XGBRegressor(
            objective="reg:squarederror",
            n_estimators=xgb.n_estimators,
            max_depth=xgb.max_depth,
            learning_rate=xgb.learning_rate,
            subsample=xgb.subsample,
            colsample_bytree=xgb.colsample_bytree,
            random_state=xgb.random_state,
            n_jobs=xgb.n_jobs,
        )

    raise ValueError(f"Unsupported regressor: {name}")


def fit_regressor(name: str, train_dataset: pd.DataFrame, target_column: str, preprocessor: FeaturePreprocessor, config: ModelConfig | None = None) -> FittedRegressor:
    X = preprocessor.transform(train_dataset)
    y = pd.to_numeric(train_dataset[target_column], errors="coerce")

    model = create_regressor(name, config=config)
    model.fit(X, y)
    return FittedRegressor(
        name=name,
        model=model,
        preprocessor=preprocessor,
        feature_columns=preprocessor.feature_columns,
    )


def top_feature_importance(fitted: FittedRegressor, limit: int = 10) -> list[dict[str, float | str]]:
    importances = getattr(fitted.model, "feature_importances_", None)
    if importances is None:
        return []

    pairs = sorted(zip(fitted.feature_columns, importances), key=lambda item: item[1], reverse=True)
    return [{"feature": feature, "importance": float(importance)} for feature, importance in pairs[:limit]]
