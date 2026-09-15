from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from stock_ai.ml.config import CLASS_LABELS, ModelConfig
from stock_ai.ml.preprocessing import FeaturePreprocessor


try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - exercised only when dependency/runtime is absent
    XGBClassifier = None


@dataclass
class FittedClassifier:
    name: str
    model: object
    preprocessor: FeaturePreprocessor
    label_encoder: LabelEncoder
    feature_columns: list[str]

    @property
    def classes_(self) -> list[str]:
        return list(self.label_encoder.classes_)

    def predict(self, dataset: pd.DataFrame) -> np.ndarray:
        X = self.preprocessor.transform(dataset)
        encoded = self.model.predict(X)
        return self.label_encoder.inverse_transform(encoded.astype(int))

    def predict_proba(self, dataset: pd.DataFrame) -> np.ndarray:
        X = self.preprocessor.transform(dataset)
        probabilities = self.model.predict_proba(X)
        return _align_probabilities(probabilities, self.model.classes_, len(self.label_encoder.classes_))


def create_classifier(name: str, config: ModelConfig | None = None):
    config = config or ModelConfig()
    normalized = name.lower()

    if normalized == "dummy":
        return DummyClassifier(strategy="most_frequent")
    if normalized == "logistic":
        return LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            random_state=config.random_state,
        )
    if normalized == "random_forest":
        return RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=config.random_state,
            n_jobs=1,
        )
    if normalized == "xgboost":
        if XGBClassifier is None:
            raise ImportError("xgboost is not installed. Install xgboost to train XGBoost classifiers.")
        xgb = config.xgboost
        return XGBClassifier(
            objective="multi:softprob",
            eval_metric="mlogloss",
            n_estimators=xgb.n_estimators,
            max_depth=xgb.max_depth,
            learning_rate=xgb.learning_rate,
            subsample=xgb.subsample,
            colsample_bytree=xgb.colsample_bytree,
            random_state=xgb.random_state,
            n_jobs=xgb.n_jobs,
        )

    raise ValueError(f"Unsupported classifier: {name}")


def fit_classifier(name: str, train_dataset: pd.DataFrame, target_column: str, preprocessor: FeaturePreprocessor, config: ModelConfig | None = None) -> FittedClassifier:
    label_encoder = LabelEncoder()
    label_encoder.fit(CLASS_LABELS)
    y = label_encoder.transform(train_dataset[target_column].astype(str))
    X = preprocessor.transform(train_dataset)

    model = create_classifier(name, config=config)
    model.fit(X, y)
    return FittedClassifier(
        name=name,
        model=model,
        preprocessor=preprocessor,
        label_encoder=label_encoder,
        feature_columns=preprocessor.feature_columns,
    )


def top_feature_importance(fitted: FittedClassifier, limit: int = 10) -> list[dict[str, float | str]]:
    importances = getattr(fitted.model, "feature_importances_", None)
    if importances is None:
        return []

    pairs = sorted(zip(fitted.feature_columns, importances), key=lambda item: item[1], reverse=True)
    return [{"feature": feature, "importance": float(importance)} for feature, importance in pairs[:limit]]


def _align_probabilities(probabilities: np.ndarray, model_classes: np.ndarray, total_classes: int) -> np.ndarray:
    aligned = np.zeros((len(probabilities), total_classes))
    for source_index, class_index in enumerate(model_classes.astype(int)):
        aligned[:, class_index] = probabilities[:, source_index]
    row_sums = aligned.sum(axis=1, keepdims=True)
    aligned = np.divide(aligned, row_sums, out=np.zeros_like(aligned), where=row_sums != 0)
    return aligned
