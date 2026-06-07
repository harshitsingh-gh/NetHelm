"""Tests for the storage layout module (Task A)."""

import json
import tempfile
from pathlib import Path

from netbrace.core.jsonio import to_json
from netbrace.storage.layout import load_suite, load_task, write_suite, write_task
from netbrace.tasks.safety.generator import GenerationSpec, generate


def _five_tasks():
    return generate(GenerationSpec(count=5))


def test_write_and_load_suite_round_trips():
    tasks = _five_tasks()
    with tempfile.TemporaryDirectory() as tmp:
        root = write_suite(tasks, tmp)
        loaded = load_suite(root)
    assert len(loaded) == 5
    orig_json = [to_json(t) for t in sorted(tasks, key=lambda t: t.task_id)]
    load_json = [to_json(t) for t in loaded]
    assert orig_json == load_json


def test_manifest_has_64_char_suite_hash():
    tasks = _five_tasks()
    with tempfile.TemporaryDirectory() as tmp:
        root = write_suite(tasks, tmp)
        manifest = json.loads((root / "manifest.json").read_text())
    assert len(manifest["suite_hash"]) == 64
    assert manifest["count"] == 5


def test_index_is_sorted_by_task_id():
    tasks = _five_tasks()
    with tempfile.TemporaryDirectory() as tmp:
        root = write_suite(tasks, tmp)
        ids = [json.loads(ln)["task_id"] for ln in (root / "_index.jsonl").read_text().splitlines()]
    assert ids == sorted(ids)


def test_write_task_and_load_task():
    tasks = _five_tasks()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tasks").mkdir()
        path = write_task(tasks[0], root)
        loaded = load_task(path)
    assert to_json(loaded) == to_json(tasks[0])


def test_suite_hash_changes_with_different_tasks():
    a = generate(GenerationSpec(count=3))
    b = generate(GenerationSpec(count=4))
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        m_a = json.loads((write_suite(a, tmp1) / "manifest.json").read_text())
        m_b = json.loads((write_suite(b, tmp2) / "manifest.json").read_text())
    assert m_a["suite_hash"] != m_b["suite_hash"]
