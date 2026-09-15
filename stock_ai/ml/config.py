from __future__ import annotations

from dataclasses import dataclass, field


CLASS_LABELS = ["DOWN", "NEUTRAL", "UP"]


@dataclass(frozen=True)
class XGBoostConfig:
    n_estimators: int = 80
    max_depth: int = 3
    learning_rate: float = 0.05
    subsample: float = 0.9
    colsample_bytree: float = 0.9
    random_state: int = 42
    n_jobs: int = 1


@dataclass(frozen=True)
class ModelConfig:
    random_state: int = 42
    xgboost: XGBoostConfig = field(default_factory=XGBoostConfig)


DEFAULT_CLASSIFICATION_MODELS = ["dummy", "logistic", "random_forest", "xgboost"]
DEFAULT_REGRESSION_MODELS = ["dummy", "ridge", "random_forest", "xgboost"]

