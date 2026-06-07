#!/usr/bin/env python
"""End-to-end demo of the D7 (forwarding anomaly / blackhole) dimension.

Requires a running Batfish on 127.0.0.1 and the [oracle] extra. Run from repo
root with the dev venv active:

    python scripts/demo_extended_blackhole.py

Builds the `blackhole` scenario on the square4 baseline, asks Batfish for the
real D7 ground truth, and shows that a model predicting only "r1 loses
reachability" (D3) misses the anomaly classification + localization that D7
captures. Writes an artifact to runs/demo_blackhole/.
"""

from __future__ import annotations

import json
from pathlib import Path

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import ExtendedBlastRadius, ForwardingAnomaly
from netbrace.core.jsonio import to_json
from netbrace.graders.extended import grade_extended
from netbrace.tasks.safety import scenario_blackhole as bh
from netbrace.topology.patches import apply_unified_diff


def main(host: str = "127.0.0.1") -> None:
    pre = bh.baseline_configs()
    post = dict(pre)
    post[bh.CHANGE_TARGET] = apply_unified_diff(post[bh.CHANGE_TARGET], bh.change_patch())

    truth = ExtendedOracle(host=host).compute_forwarding(pre, post, bh.PROBE_FLOWS)

    naive = ExtendedBlastRadius()  # predicts no forwarding anomaly
    aware = ExtendedBlastRadius(
        forwarding_anomalies=[
            ForwardingAnomaly(node="r1", dst_prefix="10.0.0.4/32", kind="blackhole")
        ]
    )
    sr_naive = grade_extended(naive, truth, task_id="bh_s15")
    sr_aware = grade_extended(aware, truth, task_id="bh_s15")

    print("Batfish D7 ground truth:", [a.key for a in truth.forwarding_anomalies])
    print(f"ext grader, naive pred : status={sr_naive.status} macro_f1={sr_naive.macro_f1}")
    print(f"ext grader, aware pred : status={sr_aware.status} macro_f1={sr_aware.macro_f1} exact={sr_aware.exact_match}")

    out = Path("runs/demo_blackhole")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ground_truth.json").write_text(to_json(truth), encoding="utf-8")
    (out / "summary.json").write_text(
        json.dumps(
            {
                "ground_truth_forwarding_anomalies": [a.key for a in truth.forwarding_anomalies],
                "ext_naive": {"status": sr_naive.status, "macro_f1": sr_naive.macro_f1},
                "ext_aware": {"status": sr_aware.status, "macro_f1": sr_aware.macro_f1,
                              "exact": sr_aware.exact_match},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}/ground_truth.json and summary.json")


if __name__ == "__main__":
    main()
