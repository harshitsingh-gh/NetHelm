#!/usr/bin/env python3
"""Build the clean N=5 Gemini grounded/no_tools dataset.

Gemini 3.5 Flash's API returns transient 503 "high demand" on a fraction of calls,
so no single run lands a clean 55/55 — but the UNION of the post-freeze runs does.
This pools those runs and selects exactly N=5 valid samples per instance,
deterministically, then computes the headline stats with the SAME two-stage
aggregator the sweep uses (netbrace.reporting.sweep_aggregate) — no hand-rolled
metrics. It writes a run-format dir that scripts/build_dashboard.py merges as the
LATEST (authoritative) Gemini source, superseding the partial per-run numbers.

Why pooling is valid HERE (and disclosed in the paper caveats): the prompt was
frozen at commit a317f3d (2026-06-10). All three source runs post-date the freeze,
so their Gemini draws are i.i.d. samples of the *same* experimental condition. Every
OTHER model is reported from a single run; only Gemini is pooled, and only because of
provider outages. The PRE-freeze run (sweep_20260610_031628) is deliberately EXCLUDED
— different prompt, not poolable.

One command, one artifact: prints the clean stats and the dir it wrote.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from netbrace.reporting.sweep_aggregate import aggregate_scenario_level

MODEL = "gemini/gemini-3.5-flash"
COND = "no_tools"
SPLIT = "grounded"
N = 5
# POST-FREEZE runs only. 031628 (pre-freeze) is intentionally absent.
SOURCES = [
    "runs/sweep_20260611_000024",   # Run B+C frontier grounded
    "runs/sweep_20260611_065948",   # detached re-run (timeout fix)
    "runs/sweep_20260611_100408",   # surgical scale_deagg top-up
]
OUT = Path("runs/sweep_zzzz_gemini_clean_postfreeze")  # sorts last -> latest -> wins


def main() -> None:
    # 1) gather every valid post-freeze Gemini grounded/no_tools draw, tagged by run.
    by_inst: dict[str, list[tuple[str, int, dict]]] = {}
    for d in SOURCES:
        rj = Path(d) / "results.jsonl"
        if not rj.exists():
            sys.exit(f"missing source run: {rj}")
        for line in rj.open():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if (r.get("kind") == "model" and r.get("model") == MODEL
                    and r.get("condition") == COND and r.get("split") == SPLIT):
                if r.get("valid_prediction") is False:
                    continue  # the clean N=5 is 5 VALID draws (Gemini invalid=0 anyway)
                by_inst.setdefault(r["instance"], []).append(
                    (Path(d).name, int(r.get("sample", 0)), r))

    # 2) deterministic selection: sort by (run, sample), take the first N per instance.
    recs: dict[str, list[dict]] = {}
    selected: list[dict] = []
    short: list[tuple[str, int]] = []
    for inst, lst in by_inst.items():
        lst.sort(key=lambda x: (x[0], x[1]))
        chosen = [r for (_, _, r) in lst[:N]]
        if len(chosen) < N:
            short.append((inst, len(chosen)))
        recs[inst] = chosen
        selected.extend(chosen)
    if short:
        sys.exit(f"ERROR: instances short of N={N} valid draws: {short}")

    # 3) aggregate with the EXACT sweep aggregator (+ the damage-only macro, mirroring
    #    run_sweep._agg: calibration instances with empty ground truth are excluded so
    #    an empty predictor can't inflate the damage headline).
    stats = aggregate_scenario_level(recs)
    dmg = {i: r for i, r in recs.items() if r and not r[0].get("gt_empty")}
    stats["macro_f1_damage"] = (
        aggregate_scenario_level(dmg)["macro_f1"] if dmg else None)
    stats["n_damage_instances"] = len(dmg)

    # 4) write the run-format dir build_dashboard will merge as latest.
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "manifest": {
            "oracle": "batfish",
            "samples_per_instance": N,
            "note": ("clean N=5 Gemini pooled from post-freeze runs "
                     + ", ".join(Path(s).name for s in SOURCES)
                     + " (provider 503 flakiness; identical frozen prompt)"),
        },
        "models": {f"{MODEL} @ {COND}": {SPLIT: stats}},
        "baselines": {},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                      encoding="utf-8")
    with (OUT / "results.jsonl").open("w", buffering=1, encoding="utf-8") as fh:
        for r in selected:
            fh.write(json.dumps(r) + "\n")

    # 5) report.
    m = stats["macro_f1"]
    fsa = stats["false_session_alarm_rate"]
    inv = stats["invalid_rate"]
    fwd = stats["by_dimension"].get("forwarding", {})
    pfx = stats["by_dimension"].get("prefixes", {})
    dmgm = stats["macro_f1_damage"]
    print(f"clean Gemini N={N} grounded — {stats['n_instances']} instances, "
          f"{len(selected)} samples ({stats['n_damage_instances']} damage instances)")
    print(f"  macro_f1    = {m['mean']:.3f} ± {m['std']:.3f}")
    print(f"  forwarding  = {fwd.get('mean_f1', 0.0):.3f}  (n_inst={fwd.get('n_instances')})")
    print(f"  prefixes    = {pfx.get('mean_f1', 0.0):.3f}  (n_inst={pfx.get('n_instances')})")
    print(f"  FSA_rate    = {fsa['mean']:.3f}")
    print(f"  invalid     = {inv['mean']:.3f}")
    print(f"  macro_dmg   = {dmgm['mean']:.3f}" if dmgm else "  macro_dmg   = n/a")
    print(f"wrote {OUT}/  (summary.json, results.jsonl)")


if __name__ == "__main__":
    main()
