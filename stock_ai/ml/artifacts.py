from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib


def make_model_version(model_name: str, task: str, horizon: str, timestamp: datetime | None = None) -> str:
    timestamp = timestamp or datetime.now(timezone.utc)
    return f"{model_name}_{task}_{horizon}_{timestamp.strftime('%Y%m%d_%H%M%S')}"


def save_model_artifact(model: Any, metadata: dict[str, Any], artifact_dir: str | Path) -> Path:
    path = Path(artifact_dir)
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path / "model.joblib")
    (path / "metadata.json").write_text(json.dumps(_json_safe(metadata), indent=2, sort_keys=True))
    return path


def load_model_artifact(artifact_dir: str | Path) -> tuple[Any, dict[str, Any]]:
    path = Path(artifact_dir)
    model = joblib.load(path / "model.joblib")
    metadata = json.loads((path / "metadata.json").read_text())
    return model, metadata


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value

