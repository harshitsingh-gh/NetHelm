"""Deterministic JSON read/write for Pydantic models. Stable byte output.

`write_model` produces sorted-key, newline-terminated JSON so that the same
object always yields the same bytes (needed for the determinism gate and suite
hashing). Always go through these helpers; never `json.dump` a model by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def to_json(model: BaseModel) -> str:
    """Canonical JSON string for a model: sorted keys, 2-space indent, trailing newline."""
    data = model.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_model(model: BaseModel, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_json(model), encoding="utf-8")
    return p


def read_model(cls: Type[T], path: str | Path) -> T:
    return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
