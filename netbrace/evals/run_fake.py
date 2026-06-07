"""Run the full pipeline with FakeModel — zero API spend, tests the whole loop."""

from __future__ import annotations

from pathlib import Path

from netbrace.core.jsonio import to_json
from netbrace.evals.parser import parse_prediction
from netbrace.graders.safety import grade
from netbrace.models.fake import FakeModel
from netbrace.storage.layout import load_suite
from netbrace.storage.run_store import create_run, write_results_csv, write_sample


def run_fake(suite_dir: str | Path, run_id: str, mode: str = "oracle") -> Path:
    """Run FakeModel over the suite, grade, and write results.csv. Returns run_dir."""
    suite_dir = Path(suite_dir)
    tasks = load_suite(suite_dir)
    model = FakeModel(mode=mode)

    run_dir = create_run(run_id)
    for task in tasks:
        raw = model.respond(task)
        pred = parse_prediction(raw)
        score = grade(
            pred,
            task.oracle.blast_radius,
            is_trap=task.meta.is_trap,
            valid_nodes=set(task.topology.nodes),
            task_id=task.task_id,
        )
        pred_json = to_json(pred) if pred is not None else "{}\n"
        write_sample(run_dir, task.task_id, raw, pred_json, score)

    write_results_csv(run_dir)
    return run_dir
