"""Persist and load a generated task suite to/from disk."""

from __future__ import annotations

import json
from pathlib import Path

from netbrace.core.hashing import suite_hash
from netbrace.core.jsonio import read_model, to_json, write_model
from netbrace.core.schemas import TaskSpec


def write_suite(tasks: list[TaskSpec], out_dir: str | Path) -> Path:
    """Write tasks to disk and return Path(out_dir).

    Layout:
      <out_dir>/tasks/<task_id>.json   — one file per task
      <out_dir>/_index.jsonl           — one line per task, sorted by task_id
      <out_dir>/manifest.json          — suite_id, suite_hash, count
    """
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(exist_ok=True)

    task_json: dict[str, str] = {}
    for task in tasks:
        rel = f"tasks/{task.task_id}.json"
        write_model(task, root / rel)
        task_json[task.task_id] = to_json(task)

    # _index.jsonl sorted by task_id
    with (root / "_index.jsonl").open("w", encoding="utf-8") as f:
        for tid in sorted(task_json):
            line = json.dumps({"task_id": tid, "path": f"tasks/{tid}.json"})
            f.write(line + "\n")

    # manifest.json
    hash_val = suite_hash(task_json[tid] for tid in sorted(task_json))
    manifest = {"suite_id": root.name, "suite_hash": hash_val, "count": len(tasks)}
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    return root


def load_suite(out_dir: str | Path) -> list[TaskSpec]:
    """Load tasks from _index.jsonl; return list sorted by task_id."""
    root = Path(out_dir)
    index_path = root / "_index.jsonl"
    tasks: list[TaskSpec] = []
    with index_path.open(encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            tasks.append(load_task(root / entry["path"]))
    return tasks


def write_task(task: TaskSpec, out_dir: str | Path) -> Path:
    """Write a single task to <out_dir>/tasks/<task_id>.json."""
    root = Path(out_dir)
    path = root / "tasks" / f"{task.task_id}.json"
    return write_model(task, path)


def load_task(path: str | Path) -> TaskSpec:
    return read_model(TaskSpec, path)
