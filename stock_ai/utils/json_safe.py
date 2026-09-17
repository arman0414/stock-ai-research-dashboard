from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def sanitize_json(value: Any) -> Any:
    """Return a JSON-safe copy with non-finite numbers converted to null."""
    if is_dataclass(value):
        return sanitize_json(asdict(value))
    if isinstance(value, dict):
        return {str(key): sanitize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return [sanitize_json(item) for item in value.tolist()]
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return sanitize_json(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def dumps_json(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("allow_nan", False)
    return json.dumps(sanitize_json(value), **kwargs)


def write_json_file(path: str | Path, value: Any, **kwargs: Any) -> None:
    Path(path).write_text(dumps_json(value, **kwargs))

