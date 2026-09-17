from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

from stock_ai.utils.json_safe import sanitize_json, write_json_file


def make_model_version(model_name: str, task: str, horizon: str, timestamp: datetime | None = None) -> str:
    timestamp = timestamp or datetime.now(timezone.utc)
    return f"{model_name}_{task}_{horizon}_{timestamp.strftime('%Y%m%d_%H%M%S')}"


def save_model_artifact(model: Any, metadata: dict[str, Any], artifact_dir: str | Path) -> Path:
    path = Path(artifact_dir)
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path / "model.joblib")
    write_json_file(path / "metadata.json", metadata, indent=2, sort_keys=True)
    return path


def load_model_artifact(artifact_dir: str | Path) -> tuple[Any, dict[str, Any]]:
    path = Path(artifact_dir)
    model = joblib.load(path / "model.joblib")
    metadata = json.loads((path / "metadata.json").read_text())
    return model, metadata


def _json_safe(value: Any) -> Any:
    return sanitize_json(value)
