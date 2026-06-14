#!/usr/bin/env python3
"""Standalone semantic-grader scorer for one model's saved sweep dir(s).

NO API calls, NO Batfish. Reads a run dir's instances.jsonl (truth + prompt) and
responses.jsonl (raw), regrades each sample under the FROZEN semantic grader
(graders.semantic_sets), and aggregates two-stage exactly like the sweep. Used to
land the new open-weight models (DeepSeek, Kimi) on the same footing as the frontier
backbone BEFORE wiring them into regrade_semantic.py.

Usage:
  score_open_model.py --model kimi/kimi-k2.6 \
      --grounded-dir runs/sweep_XXXX --reroute-dir runs/sweep_YYYY
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from netbrace.core.dimensions import EXT_ELEMENT_TYPES
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.semantic_sets import config_visible_prefixes, grade_keysets_semantic
from netbrace.reporting.baselines import empty_keysets
from netbrace.reporting.sweep_aggregate import aggregate_scenario_level


def _load_instances(d: Path) -> dict:
    inst = {}
    for line in (d / "instances.jsonl").open():
        r = json.loads(line)
        truth = {t: set(v) for t, v in r["truth"].items()}
        for t in EXT_ELEMENT_TYPES:
            truth.setdefault(t, set())
        prompt = r["prompts"].get("no_tools") or next(iter(r["prompts"].values()))
        inst[r["instance"]] = {"truth": truth, "is_trap": r["is_trap"],
                               "gt_empty": r["gt_empty"], "split": r["split"],
                               "cfg": config_visible_prefixes(prompt)}
    return inst


def _load_raw(d: Path, model: str) -> dict:
    out = {}
    f = d / "responses.jsonl"
    if f.exists():
        for line in f.open():
            r = json.loads(line)
            if r.get("model") == model:
                out[(r["instance"], int(r["sample"]))] = r["raw"]
    return out


def _grade(model: str, d: Path):
    """Return records[instance] -> list of graded sample dicts (semantic)."""
    inst = _load_instances(d)
    raw = _load_raw(d, model)
    recs = defaultdict(list)
    n_inv = 0
    for (iid, samp), txt in sorted(raw.items()):
        meta = inst[iid]
        po = parse_extended_prediction(txt)
        valid = po is not None
        if not valid:
            n_inv += 1
        predks = ({t: set(v) for t, v in po.key_sets().items()} if po else empty_keysets())
        g = grade_keysets_semantic(predks, meta["truth"], config_prefixes=meta["cfg"],
                                   is_trap=meta["is_trap"],
                                   task_id=f"{iid}|{model}|s{samp}",
                                   valid_prediction=valid).model_dump()
        g["gt_empty"] = meta["gt_empty"]
        recs[iid].append(g)
    return recs, inst, n_inv, len(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--grounded-dir")
    ap.add_argument("--reroute-dir")
    a = ap.parse_args()

    print(f"=== SEMANTIC SCORE: {a.model} ===\n")

    if a.grounded_dir:
        recs, inst, n_inv, n_tot = _grade(a.model, REPO / a.grounded_dir)
        stats = aggregate_scenario_level({i: v for i, v in recs.items() if v})
        dmg = {i: v for i, v in recs.items() if v and not v[0]["gt_empty"]}
        dmg_macro = aggregate_scenario_level(dmg)["macro_f1"]["mean"] if dmg else None
        m = stats["macro_f1"]
        print(f"GROUNDED ({n_tot} samples, {n_inv} invalid, {len(recs)} instances)")
        print(f"  macro-F1 = {m['mean']:.3f} ± {m['std']:.3f}   damage-macro = {dmg_macro:.3f}")
        print(f"  FSA = {stats.get('false_session_alarm_rate',{}).get('mean',0):.3f}   "
              f"invalid = {stats.get('invalid_rate',{}).get('mean',0):.3f}")
        print("  by-dimension mean F1:")
        for dim, dd in sorted(stats.get("by_dimension", {}).items()):
            print(f"    {dim:<14} {dd['mean_f1']:.3f} ±{dd['std_f1']:.3f}  (n={dd['n_instances']})")
        # F1-where-truth on the specific grounded keystones (paper Table 2 style)
        print("  F1 where the dimension IS the ground truth (recall-style keystones):")
        for iid, dim in [("clos_summary", "forwarding"), ("ipc3_static", "bgp_withdrawn"),
                         ("mgmt_lockout", "intent")]:
            if iid in recs:
                vals = [s["per_type"].get(dim, {}).get("f1", 0) for s in recs[iid]]
                print(f"    {iid:<16} {dim:<12} mean F1 = {sum(vals)/len(vals):.3f} (n={len(vals)})")

    if a.reroute_dir:
        recs, inst, n_inv, n_tot = _grade(a.model, REPO / a.reroute_dir)
        print(f"\nREROUTE — silent waypoint bypass ({n_tot} samples, {n_inv} invalid, "
              f"{len(recs)} instances)")
        way_all, both_zero, n = [], 0, 0
        for iid in sorted(recs):
            wv = [s["per_type"].get("waypoint", {}).get("f1", 0) for s in recs[iid]]
            iv = [s["per_type"].get("intent", {}).get("f1", 0) for s in recs[iid]]
            bz = sum(1 for w, i in zip(wv, iv) if w == 0 and i == 0)
            print(f"    {iid:<38} waypoint mean={sum(wv)/len(wv):.2f}  both-zero={bz}/{len(wv)}")
            way_all += wv; both_zero += bz; n += len(wv)
        print(f"  >> waypoint mean F1 = {sum(way_all)/len(way_all):.3f}   "
              f"BOTH-ZERO (complete miss) = {both_zero}/{n}")
        verdict = ("READS the reroute" if both_zero / n < 0.34
                   else "MOSTLY MISSES the reroute" if both_zero / n < 0.84
                   else "MISSES the reroute")
        print(f"  >> verdict: {a.model} {verdict} ({both_zero}/{n} samples completely miss)")


if __name__ == "__main__":
    main()
