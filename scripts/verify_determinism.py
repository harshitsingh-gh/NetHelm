#!/usr/bin/env python
"""Determinism gate for the unified ExtendedOracle, run against LIVE Batfish.

For EVERY scenario in ``netbrace.tasks.safety.scenarios.REGISTRY`` — plus, with
``--generated N``, the first N templated instances from the generated suite (the
split the sweep actually scores; audit 2026-06-10 K4) — this runs
``ExtendedOracle.compute_checked(scn, runs=N)`` (default N=10) and prints a
PASS/FAIL table:

    scenario -> stable? -> sha256(canonical-key-sets) -> #elements

A scenario is PASS only if all N runs are byte-identical (the doctrine's
">=10x byte-identical or quarantine" bar). Any FAIL is a critical finding: it is
reported loudly with the differing dimension and the script exits non-zero.

Each scenario gets a FRESH Batfish network (``detgate_<name>``). The previous
design reused ONE network across all scenarios "to prove reuse is clean" — that
was disproven (audit 2026-06-10 K4): ~240 snapshot inits on one network wedge the
Batfish coordinator ("Found no active locations" -> cascading 400s), making the
gate itself non-re-runnable. Per-scenario isolation is the verified-clean mode.
A known transient Batfish flake ("Work terminated abnormally") is retried once
with a fresh network name before a scenario is declared FAILED.

One artifact: ``runs/determinism_<ts>/report.json``.

Requires a running Batfish (default 127.0.0.1) and the [oracle] extra.

    python scripts/verify_determinism.py
    python scripts/verify_determinism.py --runs 10 --host 127.0.0.1
    python scripts/verify_determinism.py --generated 96 --seed 0   # gate the sweep's split
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from netbrace.batfish.extended_oracle import (
    ExtendedOracle,
    NonDeterministicOracleError,
    assert_extended_deterministic,
)
from netbrace.core.jsonio import to_json
from netbrace.tasks.safety import scenarios

_ROOT = Path(__file__).resolve().parents[1]


def _key_sets_sha(result) -> str:
    """A stable sha256 over the sorted key sets of an ExtendedBlastRadius."""
    ks = {dim: sorted(keys) for dim, keys in result.key_sets().items()}
    blob = json.dumps(ks, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _full_sha(result) -> str:
    """sha256 over the full canonical JSON (catches payload drift too)."""
    return hashlib.sha256(to_json(result).encode("utf-8")).hexdigest()


def _gate_one(scn, host: str, runs: int) -> dict:
    """Gate ONE scenario on a FRESH network; retry transient flakes once."""
    name = scn.name
    t0 = time.time()
    last_err: Exception | None = None
    for attempt in range(2):  # one retry for the known transient Batfish flake
        oracle = ExtendedOracle(host=host, network=f"detgate_{name}_a{attempt}")
        try:
            results = [oracle.compute(scn) for _ in range(runs)]
            stable = assert_extended_deterministic(results, scenario_name=name)
            return {
                "scenario": name,
                "runs": runs,
                "stable": True,
                "key_sets_sha": _key_sets_sha(stable),
                "full_sha": _full_sha(stable),
                "elements": sum(len(s) for s in stable.key_sets().values()),
                "active_dims": sorted(d for d, s in stable.key_sets().items() if s),
                "seconds": round(time.time() - t0, 1),
                "error": None,
            }
        except NonDeterministicOracleError as e:
            last_err = e
            break  # genuine divergence — never retried away
        except Exception as e:  # noqa: BLE001 — transient Batfish flake; retry fresh
            last_err = e
            print(f"  [flake-retry] {name}: {e}", flush=True)
    return {
        "scenario": name,
        "runs": runs,
        "stable": False,
        "key_sets_sha": None,
        "full_sha": None,
        "elements": None,
        "active_dims": None,
        "seconds": round(time.time() - t0, 1),
        "error": str(last_err),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--generated", type=int, default=0,
                    help="ALSO gate the first N templated instances of the generated "
                         "suite (must cover whatever --n-generated the sweep uses; "
                         "no number ships over un-gated instances).")
    ap.add_argument("--seed", type=int, default=0,
                    help="base seed for --generated (must match the sweep's --seed)")
    args = ap.parse_args()

    scns = [scenarios.build(name) for name in sorted(scenarios.REGISTRY)]
    if args.generated:
        # Same multi-mechanism suite the sweep scores (run_sweep.build_instances).
        scns += list(scenarios.build_generated_suite_multi(args.generated,
                                                           base_seed=args.seed))

    rows = []
    all_pass = True
    for scn in scns:
        row = _gate_one(scn, args.host, args.runs)
        if not row["stable"]:
            all_pass = False
        rows.append(row)

    # --- table ---
    print(f"\nDETERMINISM GATE  (runs={args.runs} each, host={args.host})")
    print("=" * 92)
    print(f"{'scenario':<16} {'stable':<7} {'#el':<4} {'sha256(key_sets)[:16]':<18} {'sec':<5} active_dims")
    print("-" * 92)
    for r in rows:
        sha = (r["key_sets_sha"] or "")[:16]
        stable = "PASS" if r["stable"] else "FAIL"
        nel = "-" if r["elements"] is None else str(r["elements"])
        dims = ",".join(r["active_dims"]) if r["active_dims"] else ("-" if r["stable"] else "")
        print(f"{r['scenario']:<16} {stable:<7} {nel:<4} {sha:<18} {r['seconds']:<5} {dims}")
    print("=" * 92)

    n_pass = sum(1 for r in rows if r["stable"])
    print(f"\n{n_pass}/{len(rows)} scenarios are >={args.runs}x byte-identical.")
    if not all_pass:
        print("\nCRITICAL: the following scenarios are NON-DETERMINISTIC (quarantine candidates):")
        for r in rows:
            if not r["stable"]:
                print(f"  - {r['scenario']}: {r['error']}")

    # --- artifact ---
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = _ROOT / "runs" / f"determinism_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": ts,
        "host": args.host,
        "runs": args.runs,
        "all_pass": all_pass,
        "n_pass": n_pass,
        "n_total": len(rows),
        "scenarios": rows,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {out_dir / 'report.json'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
