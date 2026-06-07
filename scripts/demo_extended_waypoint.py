#!/usr/bin/env python
"""End-to-end demo of the D4 (waypoint) blast-radius dimension with a LIVE oracle.

Requires a running Batfish on 127.0.0.1:9996/9997 and the [oracle] extra
(pybatfish). Run from the repo root with the dev venv active:

    source harness/venvs/nethelm/bin/activate
    python scripts/demo_extended_waypoint.py

It builds the waypoint4 scenario (S18), asks Batfish for the real D4 ground
truth, then contrasts the v0 grader (blind to path changes) with the extended
grader, and writes an artifact to runs/demo_waypoint/.
"""

from __future__ import annotations

import json
from pathlib import Path

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import ExtendedBlastRadius, WaypointViolation
from netbrace.core.jsonio import to_json
from netbrace.core.schemas import BlastRadius
from netbrace.graders.extended import grade_extended
from netbrace.graders.safety import grade as grade_v0
from netbrace.tasks.safety import baseline_waypoint4 as wp
from netbrace.topology.patches import apply_unified_diff


def main(host: str = "127.0.0.1") -> None:
    pre = wp.baseline_configs()
    post = dict(pre)
    post[wp.CHANGE_TARGET] = apply_unified_diff(post[wp.CHANGE_TARGET], wp.change_patch())

    truth = ExtendedOracle(host=host).compute_waypoint(pre, post, wp.WAYPOINT_INTENTS)

    naive = ExtendedBlastRadius()  # a D1-D3-only model predicts "nothing breaks"
    aware = ExtendedBlastRadius(
        waypoint_violations=[
            WaypointViolation(src_node=s, dst_prefix=d, waypoint=w)
            for (s, d, w) in wp.WAYPOINT_INTENTS
        ]
    )

    sr_v0 = grade_v0(BlastRadius(), truth.base, task_id="wp_s18")
    sr_naive = grade_extended(naive, truth, task_id="wp_s18")
    sr_aware = grade_extended(aware, truth, task_id="wp_s18")

    print("Batfish D4 ground truth:", [v.key for v in truth.waypoint_violations])
    print(f"v0 grader,  empty pred : status={sr_v0.status} macro_f1={sr_v0.macro_f1}  (blind)")
    print(f"ext grader, naive pred : status={sr_naive.status} macro_f1={sr_naive.macro_f1}")
    print(f"ext grader, aware pred : status={sr_aware.status} macro_f1={sr_aware.macro_f1} exact={sr_aware.exact_match}")

    out = Path("runs/demo_waypoint")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ground_truth.json").write_text(to_json(truth), encoding="utf-8")
    (out / "summary.json").write_text(
        json.dumps(
            {
                "ground_truth_waypoint_violations": [v.key for v in truth.waypoint_violations],
                "v0_empty": {"status": sr_v0.status, "macro_f1": sr_v0.macro_f1},
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
