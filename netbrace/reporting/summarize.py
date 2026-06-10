"""Aggregate results.csv into summary statistics and write summary.json."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from netbrace.graders.extended import SCORED_TYPES


def summarize_extended(run_dirs: list[str | Path]) -> dict:
    """Aggregate a set of extended-scenario ``score.json`` files into a
    PER-DIMENSION report — so every scored dimension (incl. D8 ``scale`` and D9
    ``bgp_withdrawn``) is surfaced, not just an overall macro_f1.

    Each ``run_dir`` contains a ``score.json`` written by
    ``scripts/run_extended_scenario.py`` (an ``ExtendedScoreRecord`` dump). Returns:
      { by_dimension: {type: {mean_f1, n}}, overall_macro_f1,
        false_session_alarm_rate, invalid_rate, count }.
    """
    records = []
    for d in run_dirs:
        p = Path(d) / "score.json"
        if p.exists():
            records.append(json.loads(p.read_text(encoding="utf-8")))
    if not records:
        raise RuntimeError("no score.json files found in the given run_dirs")

    by_dim: dict[str, list[float]] = {t: [] for t in SCORED_TYPES}
    for r in records:
        for t, m in (r.get("per_type") or {}).items():
            if t in by_dim:
                by_dim[t].append(float(m["f1"]))
    by_dimension = {
        t: {"mean_f1": round(sum(v) / len(v), 6), "n": len(v)}
        for t, v in by_dim.items() if v
    }
    macros = [float(r["macro_f1"]) for r in records]
    n = len(records)
    return {
        "by_dimension": by_dimension,
        "overall_macro_f1": round(sum(macros) / n, 6),
        "false_session_alarm_rate": round(
            sum(1 for r in records if r.get("false_session_alarm")) / n, 6),
        "invalid_rate": round(
            sum(1 for r in records if not r.get("valid_prediction", True)) / n, 6),
        "count": n,
    }


def summarize(run_dir: str | Path) -> dict:
    """Compute aggregates from results.csv and write summary.json.

    Returns a dict with: overall_macro_f1, by_intent (dict), invalid_rate,
    false_alarm_rate, count.
    """
    run_dir = Path(run_dir)
    csv_path = run_dir / "results.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if not rows:
        raise RuntimeError(f"results.csv is empty: {csv_path}")

    macro_f1s = [float(r["macro_f1"]) for r in rows]
    invalids = sum(1 for r in rows if r["invalid"] == "True")
    false_alarms = sum(1 for r in rows if r["false_alarm"] == "True")

    by_intent: dict[str, list[float]] = {}
    for r in rows:
        by_intent.setdefault(r["intent"], []).append(float(r["macro_f1"]))
    by_intent_mean = {k: round(sum(v) / len(v), 6) for k, v in by_intent.items()}

    summary = {
        "overall_macro_f1": round(sum(macro_f1s) / len(macro_f1s), 6),
        "by_intent": by_intent_mean,
        "invalid_rate": round(invalids / len(rows), 6),
        "false_alarm_rate": round(false_alarms / len(rows), 6),
        "count": len(rows),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary
