from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from stock_ai.ml.classifiers import FittedClassifier
from stock_ai.ml.evaluation import classification_metrics


def calibrate_classifier(
    fitted: FittedClassifier,
    validation_dataset: pd.DataFrame,
    target_column: str,
    method: str = "sigmoid",
) -> FittedClassifier:
    X_validation = fitted.preprocessor.transform(validation_dataset)
    y_validation = fitted.label_encoder.transform(validation_dataset[target_column].astype(str))
    calibrated = CalibratedClassifierCV(fitted.model, method=method, cv="prefit")
    calibrated.fit(X_validation, y_validation)
    return FittedClassifier(
        name=f"{fitted.name}_calibrated",
        model=calibrated,
        preprocessor=fitted.preprocessor,
        label_encoder=fitted.label_encoder,
        feature_columns=fitted.feature_columns,
    )


def compare_calibration(
    original: FittedClassifier,
    calibrated: FittedClassifier,
    test_dataset: pd.DataFrame,
    target_column: str,
) -> dict[str, dict]:
    y_true = test_dataset[target_column].astype(str)
    original_pred = original.predict(test_dataset)
    calibrated_pred = calibrated.predict(test_dataset)
    original_proba = original.predict_proba(test_dataset)
    calibrated_proba = calibrated.predict_proba(test_dataset)

    return {
        "original": classification_metrics(y_true, original_pred, original_proba, labels=list(original.label_encoder.classes_)),
        "calibrated": classification_metrics(y_true, calibrated_pred, calibrated_proba, labels=list(calibrated.label_encoder.classes_)),
    }

