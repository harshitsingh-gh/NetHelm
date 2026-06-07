"""Aggregate results.csv into summary statistics and write summary.json."""

from __future__ import annotations

import csv
import json
from pathlib import Path


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
