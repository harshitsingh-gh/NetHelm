"""Tests for run_store and FakeModel (Task D)."""

import csv
import tempfile
from pathlib import Path

from netbrace.core.schemas import BlastRadius, Oracle, ScoreRecord, SessionLost
from netbrace.graders.safety import grade
from netbrace.models.fake import FakeModel
from netbrace.storage.run_store import create_run, write_results_csv, write_sample
from netbrace.tasks.safety.generator import GenerationSpec, generate


# ---- FakeModel unit tests ----

def test_fake_oracle_mode_parses():
    from netbrace.evals.parser import parse_prediction

    tasks = generate(GenerationSpec(count=1))
    t = tasks[0]
    raw = FakeModel("oracle").respond(t)
    pred = parse_prediction(raw)
    assert pred is not None


def test_fake_garbage_mode_returns_non_json():
    from netbrace.evals.parser import parse_prediction

    tasks = generate(GenerationSpec(count=1))
    raw = FakeModel("garbage").respond(tasks[0])
    assert parse_prediction(raw) is None


def test_fake_empty_mode_returns_empty_blast_radius():
    from netbrace.evals.parser import parse_prediction

    tasks = generate(GenerationSpec(count=1))
    raw = FakeModel("empty").respond(tasks[0])
    pred = parse_prediction(raw)
    assert pred is not None and pred.is_empty()


# ---- run_store unit tests ----

def _make_score(task_id: str) -> ScoreRecord:
    truth = BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    return grade(truth, truth, task_id=task_id)


def test_write_and_read_sample():
    sr = _make_score("safety.bgp.shut_neighbor.square4.0001")
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = create_run("test_run", runs_root=tmp)
        write_sample(run_dir, sr.task_id, "raw text", '{"sessions_lost":[]}', sr)
        raw = (run_dir / "tasks" / sr.task_id / "response.raw.txt").read_text()
        assert raw == "raw text"


def test_write_results_csv_columns():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = create_run("csv_test", runs_root=tmp)
        for i in range(3):
            tid = f"safety.bgp.shut_neighbor.square4.{i:04d}"
            write_sample(run_dir, tid, "raw", "{}", _make_score(tid))
        csv_path = write_results_csv(run_dir)
        rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 3
    expected_cols = {
        "task_id", "intent", "status", "macro_f1", "micro_f1",
        "exact_match", "is_trap", "false_alarm", "invalid",
        "sessions_f1", "prefixes_f1", "reachability_f1",
    }
    assert expected_cols <= set(rows[0].keys())
