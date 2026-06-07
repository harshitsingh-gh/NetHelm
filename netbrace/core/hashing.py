"""SHA-256 helpers for prompt hashing, suite hashing, and the determinism gate."""

from __future__ import annotations

import hashlib
from typing import Iterable


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def suite_hash(task_json_strings: Iterable[str]) -> str:
    """Order-independent hash of a set of canonical task JSON strings.

    Pass each task's canonical JSON (from jsonio.to_json). Sorting makes the
    result independent of file iteration order.
    """
    h = hashlib.sha256()
    for s in sorted(task_json_strings):
        h.update(s.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()
