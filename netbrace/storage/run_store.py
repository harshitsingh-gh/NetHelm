"""Persist model responses, parsed predictions, and scores for a single eval run."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from netbrace.core.jsonio import to_json, write_model
from netbrace.core.schemas import RunManifest, ScoreRecord


def create_run(run_id: str, runs_root: str | Path = "runs") -> Path:
    run_dir = Path(runs_root) / run_id
    (run_dir / "tasks").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_sample(
    run_dir: str | Path,
    task_id: str,
    raw_text: str,
    prediction_json: str,
    score: ScoreRecord,
) -> None:
    """Write response.raw.txt, response.parsed.json, score.json for one task."""
    d = Path(run_dir) / "tasks" / task_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "response.raw.txt").write_text(raw_text, encoding="utf-8")
    (d / "response.parsed.json").write_text(prediction_json, encoding="utf-8")
    write_model(score, d / "score.json")


def write_results_csv(run_dir: str | Path) -> Path:
    """Collect all score.json files and write results.csv."""
    run_dir = Path(run_dir)
    rows: list[dict] = []
    for score_path in sorted((run_dir / "tasks").glob("*/score.json")):
        sr = ScoreRecord.model_validate_json(score_path.read_text(encoding="utf-8"))
        row: dict = {
            "task_id": sr.task_id,
            "intent": _intent_from_task_id(sr.task_id),
            "status": sr.status,
            "macro_f1": round(sr.macro_f1, 6),
            "micro_f1": round(sr.micro_f1, 6),
            "exact_match": sr.exact_match,
            "is_trap": sr.is_trap,
            "false_alarm": sr.false_alarm,
            "invalid": sr.status == "invalid",
            "sessions_f1": round(sr.per_type.get("sessions", _zero()).f1, 6),
            "prefixes_f1": round(sr.per_type.get("prefixes", _zero()).f1, 6),
            "reachability_f1": round(sr.per_type.get("reachability", _zero()).f1, 6),
        }
        rows.append(row)
    if not rows:
        raise RuntimeError(f"no score.json files found under {run_dir}/tasks/")
    csv_path = run_dir / "results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def write_run_manifest(run_dir: str | Path, manifest: RunManifest) -> Path:
    """Persist a ``RunManifest`` (schema ``nethelm.run_manifest.v0``) for a single
    v0-suite task run — one scenario evaluated by one model call via the CLI
    (``netbrace safety oracle`` / ``netbrace eval run``).

    SCOPE: this is the PER-TASK manifest for the v0 CLI pipeline.  It is NOT the
    sweep-level provenance record.  ``scripts/run_sweep.py`` emits its own richer
    ``run_manifest.json`` (schema ``netbrace.sweep_manifest.v1``) that covers the
    full model fleet, Batfish image digest, git provenance, prompt hash, and every
    instance graded in a sweep run.  The two are intentionally different formats for
    different scopes; they must not be conflated.

    Callers: ``netbrace/cli.py`` (the v0 CLI pipeline).
    """
    path = Path(run_dir) / "run_manifest.json"
    return write_model(manifest, path)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _intent_from_task_id(task_id: str) -> str:
    parts = task_id.split(".")
    return parts[2] if len(parts) > 2 else ""


class _zero:
    f1 = 0.0
