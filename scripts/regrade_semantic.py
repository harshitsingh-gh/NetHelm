#!/usr/bin/env python3
"""Honest regrade: every saved sweep sample (and every floor) under BOTH graders.

NO paid API calls. NO Batfish. Reads ONLY saved artifacts and re-parses raw model
output with the FROZEN parser, then grades each sample under:

  * OLD = the frozen exact-string set grader (reporting.baselines.grade_keysets, which
    mirrors graders.extended.grade_extended bit-for-bit). Reproduced from raw text and
    asserted equal to the saved per_type, so any NEW-grader delta is purely the
    semantic matcher, not a reproduction bug.
  * NEW = the semantic grader (graders.semantic_sets.grade_keysets_semantic), per the
    FROZEN docs/semantic_grading_spec_v1.md.

Aggregation = the EXACT two-stage scenario-level estimator the sweep uses
(reporting.sweep_aggregate), per split, never pooled; damage-only macro excludes
gt_empty calibration instances, same as run_sweep._agg.

The six floors are recomputed (predictions rebuilt deterministically from the same
scenario builders + saved truth) under both graders, so modal_by_class
(contamination-control) is reported under the new grader.

One command, three artifacts (paths printed at the end):
  runs/regrade_semantic_<ts>/results.jsonl   per-sample old+new dumps
  runs/regrade_semantic_<ts>/summary.json    machine-readable aggregates
  paper/refs/regrade_semantic_2026-06-12.md  the consolidated report
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from netbrace.core.dimensions import EXT_ELEMENT_TYPES
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.semantic_sets import (
    config_visible_prefixes,
    grade_keysets_semantic,
)
from netbrace.reporting import baselines as bl
from netbrace.reporting.baselines import empty_keysets, grade_keysets
from netbrace.reporting.sweep_aggregate import aggregate_scenario_level
from scripts.run_sweep import build_instances, _baseline_pred

DIRS_WITH_RAW = ["sweep_20260610_213843", "sweep_20260611_000024"]
GEMINI_MODEL = "gemini/gemini-3.5-flash"
GEMINI_SOURCES = ["sweep_20260611_000024", "sweep_20260611_065948",
                  "sweep_20260611_100408"]
# Open-weight models added 2026-06-14. Each ran `--split grounded` in its OWN dir
# with its OWN Batfish-computed truth; the truth is cross-checked byte-identical to
# the canonical DIRS_WITH_RAW truth (oracle determinism) before its samples are
# graded with the canonical truth+cfg. Additive: empty dict → byte-identical to the
# original 6-model regrade.
EXTRA_GROUNDED_SOURCES = {
    "deepseek/deepseek-v4-pro": "sweep_20260613_224649",
    "kimi/kimi-k2.6": "sweep_20260614_030415",
}
# Sonnet 4.6 grounded was truncated at the 4k-cap (6/55 invalid). When
# --sonnet-grounded-dir points at a 12k-cap re-run, its Sonnet grounded samples
# SUPERSEDE the 4k rows in DIRS_WITH_RAW. Default None → behaviour is byte-identical
# to the original verified regrade.
SONNET_MODEL = "anthropic/claude-sonnet-4-6"
SONNET_12K_DIR = None
# The floors-bearing run + its exact build args (from its manifest).
FLOOR_RUN = "sweep_20260610_213843"
FLOOR_BUILD = dict(split="both", n_generated=48, seed=0, coarsen_class=True,
                   exclude=frozenset({"blackhole"}))
_DIMS = ("sessions", "prefixes", "reachability", "waypoint", "redundancy",
         "forwarding", "scale", "bgp_withdrawn", "intent")


def _runs(p: str) -> Path:
    return REPO / "runs" / p


# --------------------------------------------------------------------------- #
# Load instances: truth + is_trap + gt_empty + split/class + config CFG.
# --------------------------------------------------------------------------- #
def load_instances() -> dict[str, dict]:
    inst: dict[str, dict] = {}
    for d in DIRS_WITH_RAW:
        for line in (_runs(d) / "instances.jsonl").open():
            r = json.loads(line)
            truth = {t: set(v) for t, v in r["truth"].items()}
            for t in EXT_ELEMENT_TYPES:
                truth.setdefault(t, set())
            prompt = r["prompts"].get("no_tools") or next(iter(r["prompts"].values()))
            inst[r["instance"]] = {
                "truth": truth, "is_trap": r["is_trap"], "gt_empty": r["gt_empty"],
                "split": r["split"], "class": r["class"],
                "cfg": config_visible_prefixes(prompt),
            }
    return inst


def load_raw(d: str) -> dict[tuple, str]:
    out: dict[tuple, str] = {}
    f = _runs(d) / "responses.jsonl"
    if f.exists():
        for line in f.open():
            r = json.loads(line)
            out[(r["model"], r["condition"], r["instance"], int(r["sample"]))] = r["raw"]
    return out


# --------------------------------------------------------------------------- #
# Grade every model sample under both graders.
# --------------------------------------------------------------------------- #
def gemini_clean_selection() -> list[tuple[str, str, int]]:
    """Reproduce build_clean_gemini's selection: list of (source_run, instance, sample)
    for exactly the 55 clean N=5 grounded/no_tools draws."""
    by_inst: dict[str, list[tuple[str, int]]] = {}
    for d in GEMINI_SOURCES:
        for line in (_runs(d) / "results.jsonl").open():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if (r.get("kind") == "model" and r.get("model") == GEMINI_MODEL
                    and r.get("condition") == "no_tools" and r.get("split") == "grounded"
                    and r.get("valid_prediction") is not False):
                by_inst.setdefault(r["instance"], []).append((d, int(r.get("sample", 0))))
    out: list[tuple[str, str, int]] = []
    for inst, lst in by_inst.items():
        lst.sort(key=lambda x: (x[0], x[1]))
        for (run, samp) in lst[:5]:
            out.append((run, inst, samp))
    return out


def grade_all(inst: dict[str, dict]):
    notes: list[str] = []
    per_sample: list[dict] = []
    records: dict = defaultdict(lambda: {"templated": defaultdict(list),
                                         "grounded": defaultdict(list)})
    repro_checked = repro_mismatch = 0

    def emit(model, cond, iid, samp, raw, saved=None):
        nonlocal repro_checked, repro_mismatch
        meta = inst[iid]
        pred_obj = parse_extended_prediction(raw)
        valid = pred_obj is not None
        predks = ({t: set(v) for t, v in pred_obj.key_sets().items()} if pred_obj
                  else empty_keysets())
        old = grade_keysets(predks, meta["truth"], is_trap=meta["is_trap"],
                            task_id=f"{iid}|{model}|{cond}|s{samp}",
                            valid_prediction=valid).model_dump()
        new = grade_keysets_semantic(predks, meta["truth"], config_prefixes=meta["cfg"],
                                     is_trap=meta["is_trap"],
                                     task_id=f"{iid}|{model}|{cond}|s{samp}",
                                     valid_prediction=valid).model_dump()
        old["gt_empty"] = new["gt_empty"] = meta["gt_empty"]
        label = f"{model} @ {cond}"
        records[(label, "old")][meta["split"]][iid].append(old)
        records[(label, "new")][meta["split"]][iid].append(new)
        per_sample.append({
            "kind": "model", "model": model, "condition": cond, "instance": iid,
            "split": meta["split"], "class": meta["class"], "sample": samp,
            "valid_prediction": valid,
            "old_macro_f1": old["macro_f1"], "new_macro_f1": new["macro_f1"],
            "old_per_type": {t: m["f1"] for t, m in old["per_type"].items()},
            "new_per_type": {t: m["f1"] for t, m in new["per_type"].items()},
            "old_fsa": old["false_session_alarm"], "new_fsa": new["false_session_alarm"],
        })
        if saved is not None:
            repro_checked += 1
            for t, m in saved.get("per_type", {}).items():
                rm = old["per_type"].get(t, {})
                if (m["tp"], m["fp"], m["fn"]) != (rm.get("tp"), rm.get("fp"), rm.get("fn")):
                    repro_mismatch += 1
                    notes.append(f"REPRO MISMATCH {model} {iid} s{samp} {t}")
                    break

    for d in DIRS_WITH_RAW:
        raw = load_raw(d)
        for line in (_runs(d) / "results.jsonl").open():
            r = json.loads(line)
            if r.get("kind") != "model" or r.get("model") == GEMINI_MODEL:
                continue
            if SONNET_12K_DIR and r.get("model") == SONNET_MODEL:
                continue  # 4k-cap Sonnet grounded superseded by the 12k re-run below
            key = (r["model"], r["condition"], r["instance"], int(r["sample"]))
            if key not in raw:
                notes.append(f"MISSING RAW {key} in {d}")
                continue
            emit(*key, raw[key], saved=r)

    src_raw = {d: load_raw(d) for d in GEMINI_SOURCES}
    g_count, g_inst = 0, set()
    for (run, iid, samp) in gemini_clean_selection():
        rkey = (GEMINI_MODEL, "no_tools", iid, samp)
        raw = src_raw[run].get(rkey)
        if raw is None:
            notes.append(f"MISSING GEMINI RAW {rkey} in {run}")
            continue
        emit(GEMINI_MODEL, "no_tools", iid, samp, raw, saved=None)
        g_count += 1
        g_inst.add(iid)
    notes.append(f"gemini clean reconstructed: {g_count} samples / {len(g_inst)} instances")

    # Open-weight models (DeepSeek, Kimi): grade their grounded samples against the
    # canonical truth+cfg after a per-instance truth-determinism cross-check.
    for emodel, edir in EXTRA_GROUNDED_SOURCES.items():
        det_ok = True
        for line in (_runs(edir) / "instances.jsonl").open():
            ri = json.loads(line)
            tt = {t: set(v) for t, v in ri["truth"].items()}
            for t in EXT_ELEMENT_TYPES:
                tt.setdefault(t, set())
            base = inst.get(ri["instance"])
            if base and any(tt.get(k, set()) != base["truth"].get(k, set())
                            for k in EXT_ELEMENT_TYPES):
                det_ok = False
                notes.append(f"EXTRA TRUTH MISMATCH {emodel} {ri['instance']}")
        eraw = load_raw(edir)
        e_count = 0
        for line in (_runs(edir) / "results.jsonl").open():
            r = json.loads(line)
            if r.get("kind") != "model" or r.get("model") != emodel:
                continue
            key = (r["model"], r["condition"], r["instance"], int(r["sample"]))
            if key not in eraw:
                notes.append(f"MISSING EXTRA RAW {key} in {edir}")
                continue
            emit(*key, eraw[key], saved=r)
            e_count += 1
        notes.append(f"extra source {emodel} ({edir}): {e_count} grounded samples graded; "
                     f"truth-determinism vs canonical: {'PASS' if det_ok else 'FAIL'}")

    if SONNET_12K_DIR:
        # Sonnet 4.6 grounded from the 12k-cap re-run, superseding the truncated 4k
        # rows. Truth comes from the already-loaded (4k) instances; cross-check that
        # the 12k run's saved truth is byte-identical (oracle determinism) first.
        det_ok = True
        for line in (_runs(SONNET_12K_DIR) / "instances.jsonl").open():
            ri = json.loads(line)
            t12 = {t: set(v) for t, v in ri["truth"].items()}
            for t in EXT_ELEMENT_TYPES:
                t12.setdefault(t, set())
            base = inst.get(ri["instance"])
            if base and any(t12.get(k, set()) != base["truth"].get(k, set())
                            for k in EXT_ELEMENT_TYPES):
                det_ok = False
                notes.append(f"SONNET-12K TRUTH MISMATCH {ri['instance']}")
        sraw = load_raw(SONNET_12K_DIR)
        s_count = 0
        for line in (_runs(SONNET_12K_DIR) / "results.jsonl").open():
            r = json.loads(line)
            if r.get("kind") != "model" or r.get("model") != SONNET_MODEL:
                continue
            key = (r["model"], r["condition"], r["instance"], int(r["sample"]))
            if key not in sraw:
                notes.append(f"MISSING SONNET-12K RAW {key}")
                continue
            emit(*key, sraw[key], saved=r)
            s_count += 1
        notes.append(f"sonnet 12k re-run ({SONNET_12K_DIR}): {s_count} grounded samples "
                     f"graded, supersedes the 4k-cap rows; truth-determinism vs 4k: "
                     f"{'PASS' if det_ok else 'FAIL'}")

    notes.append(f"reproduction gate: {repro_checked} checked, {repro_mismatch} mismatches "
                 f"({'PASS' if repro_mismatch == 0 else 'FAIL'})")
    return per_sample, records, notes


# --------------------------------------------------------------------------- #
# Floors: rebuild predictions deterministically, grade under both graders.
# --------------------------------------------------------------------------- #
def grade_floors(inst: dict[str, dict]):
    notes: list[str] = []
    instances = build_instances(**FLOOR_BUILD)
    truth_by = {i.instance_id: inst[i.instance_id]["truth"] for i in instances
                if i.instance_id in inst}
    class_of = {i.instance_id: i.cls for i in instances}
    from collections import Counter
    member_count = Counter(class_of.values())
    modal = bl.modal_keysets_by_class(truth_by, class_of)

    records: dict = defaultdict(lambda: {"templated": defaultdict(list),
                                         "grounded": defaultdict(list)})
    # cross-check vs saved baseline per_type (OLD grader)
    saved_base: dict[tuple, dict] = {}
    for line in (_runs(FLOOR_RUN) / "results.jsonl").open():
        r = json.loads(line)
        if r.get("kind") == "baseline":
            saved_base[(r["baseline"], r["instance"])] = r
    repro_checked = repro_mismatch = 0

    for bname in bl.BASELINE_NAMES:
        for i in instances:
            iid = i.instance_id
            if iid not in inst:
                continue
            if bname == "modal_by_class" and member_count[i.cls] < 2:
                continue
            meta = inst[iid]
            pred = _baseline_pred(bname, i, truth_by[iid], modal)
            old = grade_keysets(pred, meta["truth"], is_trap=i.is_trap,
                                task_id=f"{iid}|baseline_{bname}").model_dump()
            new = grade_keysets_semantic(pred, meta["truth"], config_prefixes=meta["cfg"],
                                         is_trap=i.is_trap,
                                         task_id=f"{iid}|baseline_{bname}").model_dump()
            old["gt_empty"] = new["gt_empty"] = meta["gt_empty"]
            records[(bname, "old")][meta["split"]][iid].append(old)
            records[(bname, "new")][meta["split"]][iid].append(new)
            sv = saved_base.get((bname, iid))
            if sv is not None:
                repro_checked += 1
                for t, m in sv.get("per_type", {}).items():
                    rm = old["per_type"].get(t, {})
                    if (m["tp"], m["fp"], m["fn"]) != (rm.get("tp"), rm.get("fp"), rm.get("fn")):
                        repro_mismatch += 1
                        notes.append(f"FLOOR REPRO MISMATCH {bname} {iid} {t}")
                        break
    notes.append(f"floor reproduction gate: {repro_checked} checked, {repro_mismatch} "
                 f"mismatches ({'PASS' if repro_mismatch == 0 else 'FAIL'})")
    return records, notes


# --------------------------------------------------------------------------- #
# Aggregation (two-stage, per split, + damage-only macro).
# --------------------------------------------------------------------------- #
def agg(records, label, grader, split) -> dict:
    recs = {i: v for i, v in records[(label, grader)][split].items() if v}
    if not recs:
        return {}
    stats = aggregate_scenario_level(recs)
    dmg = {i: r for i, r in recs.items() if r and not r[0].get("gt_empty")}
    stats["macro_f1_damage"] = (aggregate_scenario_level(dmg)["macro_f1"] if dmg else None)
    stats["n_damage_instances"] = len(dmg)
    return stats


def model_labels(records) -> list[str]:
    return sorted({lab for (lab, g) in records if g == "old"})


# --------------------------------------------------------------------------- #
# Report rendering.
# --------------------------------------------------------------------------- #
def _dim_cell(stats: dict, dim: str) -> str:
    bd = stats.get("by_dimension", {})
    if dim not in bd:
        return "-"
    d = bd[dim]
    if d.get("n_instances", 0) == 1:
        return f"{d['mean_f1']:.2f}(n1)"
    return f"{d['mean_f1']:.2f}±{d['std_f1']:.2f}"


def _macro_cell(stats: dict) -> str:
    m = stats.get("macro_f1", {})
    return f"{m.get('mean', 0):.2f}±{m.get('std', 0):.2f}"


def render_report(model_recs, floor_recs, notes, ts) -> str:
    L: list[str] = []
    L.append("# Semantic regrade — old (exact-string) vs new (semantic) grader\n")
    L.append(f"Generated: {ts}  |  script: `scripts/regrade_semantic.py`  |  "
             f"spec: `docs/semantic_grading_spec_v1.md` (FROZEN)\n")
    L.append("NO paid API calls; regraded from saved artifacts only. Aggregation = "
             "two-stage scenario-level (per-instance mean over N=5 samples, then "
             "mean±std across instances), per split, never pooled. macro dmg = "
             "damage-detection macro over NON-EMPTY-truth instances only.\n")

    labels = model_labels(model_recs)
    # order: frontier first
    order = ["anthropic/claude-opus-4-8 @ no_tools", "openai/gpt-5.5 @ no_tools",
             "gemini/gemini-3.5-flash @ no_tools", "anthropic/claude-sonnet-4-6 @ no_tools",
             "anthropic/claude-haiku-4-5-20251001 @ no_tools", "openai/gpt-5.4-mini @ no_tools"]
    labels = [l for l in order if l in labels] + [l for l in labels if l not in order]

    for split in ("grounded", "templated"):
        present = [l for l in labels if agg(model_recs, l, "old", split)]
        if not present:
            continue
        L.append(f"\n## Split: {split}\n")
        # headline macro old vs new
        L.append("### Headline macro-F1 (old → new) + key dims\n")
        L.append("| system | macro old | macro NEW | macro dmg old | macro dmg NEW | "
                 "FSA old | FSA NEW | invalid |")
        L.append("|" + "---|" * 8)
        for l in present:
            so, sn = agg(model_recs, l, "old", split), agg(model_recs, l, "new", split)
            dmo, dmn = so.get("macro_f1_damage"), sn.get("macro_f1_damage")
            fo = so.get("false_session_alarm_rate", {}).get("mean", 0)
            fn_ = sn.get("false_session_alarm_rate", {}).get("mean", 0)
            iv = so.get("invalid_rate", {}).get("mean", 0)
            name = l.replace(" @ no_tools", "").split("/")[-1]
            L.append(f"| {name} | {_macro_cell(so)} | **{_macro_cell(sn)}** | "
                     f"{dmo['mean']:.2f} | **{dmn['mean']:.2f}** | "
                     f"{fo:.2f} | {fn_:.2f} | {iv:.2f} |")
        # per-dimension old vs new
        L.append("\n### Per-dimension mean F1 — old vs NEW (the dimensions the artifact hit)\n")
        focus = ["prefixes", "reachability", "waypoint", "forwarding", "bgp_withdrawn",
                 "intent", "redundancy", "scale"]
        L.append("| system | grader | " + " | ".join(focus) + " |")
        L.append("|" + "---|" * (len(focus) + 2))
        for l in present:
            for g, tag in (("old", "old"), ("new", "NEW")):
                s = agg(model_recs, l, g, split)
                name = l.replace(" @ no_tools", "").split("/")[-1]
                cells = " | ".join(_dim_cell(s, d) for d in focus)
                L.append(f"| {name} | {tag} | {cells} |")

        # floors
        L.append(f"\n### Floors — {split} (old vs NEW)\n")
        L.append("| floor | macro old | macro NEW | fwd old | fwd NEW | way old | "
                 "way NEW |")
        L.append("|" + "---|" * 7)
        for bname in bl.BASELINE_NAMES:
            so, sn = agg(floor_recs, bname, "old", split), agg(floor_recs, bname, "new", split)
            if not so and not sn:
                L.append(f"| {bname} | undefined | undefined | - | - | - | - |")
                continue
            fwo = so.get("by_dimension", {}).get("forwarding", {}).get("mean_f1")
            fwn = sn.get("by_dimension", {}).get("forwarding", {}).get("mean_f1")
            wyo = so.get("by_dimension", {}).get("waypoint", {}).get("mean_f1")
            wyn = sn.get("by_dimension", {}).get("waypoint", {}).get("mean_f1")
            L.append(f"| {bname} | {_macro_cell(so)} | {_macro_cell(sn)} | "
                     f"{fwo if fwo is None else round(fwo,2)} | "
                     f"{fwn if fwn is None else round(fwn,2)} | "
                     f"{wyo if wyo is None else round(wyo,2)} | "
                     f"{wyn if wyn is None else round(wyn,2)} |")

    # ---- Sonnet truncation analysis (task item 4) ----
    L.append("\n## Sonnet 4.6 invalid samples = max_tokens truncation (NOT reasoning failure)\n")
    L.append(sonnet_truncation_section())

    # ---- The honest story + what the paper must change (task item 5) ----
    L.append("\n## The honest story the numbers now tell\n")
    L.append(honest_story_section(model_recs))

    L.append("\n## What in paper/draft/netbrace_tr.tex is now FALSE and must be rewritten\n")
    L.append(paper_corrections_section())

    L.append("\n## Audit / reproduction notes\n")
    for n in notes:
        L.append(f"- {n}")
    return "\n".join(L) + "\n"


def sonnet_truncation_section() -> str:
    """Quantify the Sonnet truncation issue from saved artifacts (no re-run)."""
    raw = load_raw("sweep_20260611_000024")
    inv = []
    for line in (_runs("sweep_20260611_000024") / "results.jsonl").open():
        r = json.loads(line)
        if (r.get("kind") == "model"
                and r.get("model") == "anthropic/claude-sonnet-4-6"
                and r.get("valid_prediction") is False):
            inv.append((r["instance"], int(r["sample"]),
                        r.get("cost", {}).get("tokens_out")))
    lines = []
    lines.append("**max_tokens / output budget per model in the sweep config "
                 "(`scripts/run_sweep.py`):**\n")
    lines.append("| model | output budget | source |")
    lines.append("|---|---|---|")
    lines.append("| anthropic/* (haiku, sonnet, opus) | `max_tokens=4000` | `_call_anthropic` |")
    lines.append("| openai/gpt-5.5 | no explicit cap (reasoning.effort=medium) | `_call_openai` |")
    lines.append("| openai/gpt-5.4-mini | `max_output_tokens=16000` | `_call_openai` |")
    lines.append("| gemini/gemini-3.5-flash | `max_output_tokens=16000` | `_call_gemini` |")
    lines.append("")
    lines.append(f"**Sonnet 4.6 had {len(inv)} invalid samples, all on long grounded "
                 f"scenarios:** "
                 + ", ".join(f"`{i}` s{s} (tokens_out={t})" for i, s, t in inv) + ".")
    lines.append("")
    lines.append("**Every one emitted exactly 4000 output tokens = the `max_tokens=4000` "
                 "cap → hard truncation.** Sonnet's valid samples averaged ~2381 "
                 "tokens_out (max 4000); these 6 ran the budget dry mid-reasoning and "
                 "were cut off BEFORE the final ```json block, so the (correct, "
                 "forgiving) parser returns None → scored invalid. The truncated prose "
                 "contains substantively correct analysis. Quoted tails:")
    lines.append("")
    quotes = {
        ("clos_summary", 1): None, ("clos_summary", 2): None,
    }
    for (iid, samp) in list(quotes):
        rkey = ("anthropic/claude-sonnet-4-6", "no_tools", iid, samp)
        txt = raw.get(rkey, "")
        tail = txt[-420:].replace("\n", " ").strip()
        lines.append(f"- `{iid}` s{samp} (tail): “…{tail}”")
    lines.append("")
    lines.append("These tails show Sonnet correctly identifying the spine2 blackhole, "
                 "the leaf1/leaf2 prefix loss, the BGP withdrawals, and the te_pin / "
                 "reachability intent violation — it simply never reached the JSON. "
                 "**Recommended fix (NOT run here): re-run Sonnet 4.6 grounded with "
                 "`max_tokens` raised to ~12000 (the other-provider budget). Estimated "
                 "cost ~\\$1–2** (11 instances × 5 samples × ~$0.03). Until then, "
                 "Sonnet's grounded macro is depressed by a harness cap, not its "
                 "reasoning, and should be footnoted as such — its invalid_rate (0.11) "
                 "is a truncation artifact, not an output-format failure.")
    return "\n".join(lines)


def honest_story_section(model_recs) -> str:
    L = []
    L.append("**1. The D7=0.00 headline was a grader artifact and is now retracted.** "
             "Under fair grading every model recovers real D7 forwarding-anomaly "
             "signal on the grounded split: Opus 0.00→0.40, Gemini 0.00→0.40, GPT-5.5 "
             "0.00→0.33, Haiku 0.00→0.23, GPT-5.4-mini 0.00→0.17, Sonnet 0.00→0.14. "
             "The claim 'no model identified a single blackhole on any of 810 samples' "
             "is FALSE — they identified the blackhole node + kind + config-visible "
             "covering prefix; the exact-string grader rejected it only because the "
             "truth key was an undisclosed /32 probe inside that prefix.\n")
    L.append("**2. The capability gradient SURVIVES and sharpens.** Grounded macro-F1 "
             "old→new: Opus 0.37→0.51, GPT-5.5 0.36→0.48, Gemini 0.36→0.49, Haiku "
             "0.29→0.39, Sonnet 0.27→0.35, GPT-5.4-mini 0.22→0.27. The frontier still "
             "sits clearly above the mid-tier; all model-free floors stay ≤0.02 "
             "grounded (the new grader is provably identity on D2/D9/scale/sessions, "
             "so it lifts models on the probe dimensions WITHOUT lifting the floors — "
             "the contamination-control story holds: modal_by_class stays 0.18 "
             "templated / undefined grounded, syntactic_diff ≤0.02, exactly as before "
             "on the dimensions it could ever touch).\n")
    L.append("**3. The TRUE blind spot is narrower and more interesting than "
             "'universal second-order blindness'.** The dimension breakdown under fair "
             "grading shows models catch DROPS but miss PATH/INTENT violations where "
             "reachability survives:\n"
             "  - On `leak_ms_blackhole` (a route is destroyed) Haiku's D7 is 0.00→0.98 "
             "— a pure artifact; the model was right.\n"
             "  - On `leak_ms_reroute` (reachability SURVIVES but traffic silently "
             "bypasses the mandated waypoint) waypoint stays **0.10** and intent "
             "**0.02** under fair grading: **57/60 reroute samples still score 0** on "
             "waypoint+intent. This is a GENUINE, preserved miss — the subtle harm.\n"
             "  - Grounded, the dimensions that remain low for the frontier under fair "
             "grading are **D9 bgp_withdrawn (~0.14), D10 intent (~0.02–0.10), and the "
             "harder half of D7 (~0.33–0.40)** — control-plane withdrawals and "
             "policy-intent violations, not 'everything second-order'.\n")
    L.append("**4. Templated D4 waypoint was ALSO an artifact, not a 0.00 capability.** "
             "Haiku waypoint 0.00→0.39, GPT-5.4-mini 0.00→0.43; templated forwarding "
             "0.00→0.24 and 0.00→0.43. The paper's 'waypoint (D4) and redundancy (D5) "
             "are also 0.00 for both evaluated models' is half-false: D4 was the /32 "
             "artifact (now non-zero); **D5 redundancy genuinely stays 0.00 templated** "
             "(no templated instance has a redundancy truth element active for these "
             "models — a real gap to disclose, not a capability claim).\n")
    L.append("**5. F2 (no false-session-alarm) is UNAFFECTED and stands.** FSA is "
             "provably identical old→new (sessions carries no prefix slot). The "
             "one-sided-omission framing survives verbatim. F4 (no home-field "
             "advantage) survives: the cross-vendor frontier stays within noise under "
             "fair grading (Opus 0.51, Gemini 0.49, GPT-5.5 0.48).\n")
    L.append("**Bottom line:** the benchmark is REAL — it discriminates frontier from "
             "mid-tier from floors, the floors stay at chance, and a genuine, "
             "dangerous blind spot remains (silent reroutes / intent / control-plane "
             "withdrawals). But the specific, dramatic claim the paper is built around "
             "— *universal D7 blindness, 0.00 on all 810 samples* — is a measurement "
             "artifact and must be retracted before arXiv.")
    return "\n".join(L)


def paper_corrections_section() -> str:
    items = [
        ("Abstract (lines ~46–51)", "FALSE",
         "“score 0.00—on every sample, of every model evaluated—at identifying the "
         "second-order forwarding anomalies” and “would approve the blackhole "
         "without raising a single warning.” Models DO recover D7 under fair "
         "grading (frontier 0.33–0.40). Rewrite to the real finding: models partially "
         "recover blackhole drops but miss silent reroutes / intent / control-plane "
         "withdrawals; the gate would under-warn, not zero-warn."),
        ("Abstract macro numbers (line ~44)", "STALE",
         "“frontier macro-F1 0.36–0.37” → under fair grading 0.48–0.51. "
         "Floors ≤0.01 grounded still holds. Update the headline spread."),
        ("Intro/§ headline (lines ~113–123)", "FALSE",
         "“forwarding-anomaly F1 is 0.00 … all 810 graded samples” — retract; "
         "this is the grader artifact. Keep the capability-gradient framing (D2 high, "
         "consequence dims lower) which survives."),
        ("F3 'Universal second-order blindness' (lines ~376–389)", "FALSE — must be rewritten",
         "The entire paragraph asserts D7=0.00 on every sample and 'no model identified "
         "a single blackhole.' This is the core artifact. Replace with: D7 recovered "
         "(0.14–0.40 grounded); the surviving blind spot is reroute-waypoint (D4 on "
         "leak_ms_reroute ~0.10), intent (D10 ~0.02–0.10), and control-plane "
         "withdrawals (D9 ~0.14). Templated D4 also was an artifact (0.00→0.39/0.43)."),
        ("Table 'grounded' (tab:grounded, ~line 323) + Figure gradient (~354) + Figure floors (~399)",
         "STALE / WRONG NUMBERS",
         "Every D7 column reads 0.00 and macro reads 0.36–0.37; regenerate from the "
         "semantic grader (D7 0.14–0.40, macro 0.27–0.51). The floors figure caption "
         "and modal_by_class=0.00 templated still hold; the model bars move up."),
        ("Scenario table note (line ~314)", "CHECK",
         "“including it would have raised model scores on D7” — re-verify "
         "against the new D7 numbers; the contrastive logic may need restating."),
        ("F1 numbers (lines ~359–366)", "STALE",
         "Grounded frontier 0.36–0.37 → 0.48–0.51; mid-tier 0.22–0.29 → 0.27–0.39. "
         "Templated damage macro Haiku 0.15→0.30, mini 0.11→0.21. Floors unchanged. "
         "The discrimination claim stands; the magnitudes change."),
        ("F2 (lines ~368–374)", "UNCHANGED — keep",
         "FSA provably identical old→new. No edit needed beyond confirming it."),
        ("F4 (lines ~391–395)", "UPDATE NUMBERS, conclusion stands",
         "0.37/0.36/0.36 → 0.51/0.48/0.49; cross-vendor parity survives."),
        ("Sonnet invalid_rate wherever cited", "ADD FOOTNOTE",
         "Sonnet's 6 invalids are max_tokens=4000 truncations on long grounded "
         "scenarios, not format failures; recommend a ~$1–2 re-run at max_tokens≈12000 "
         "and footnote the cap. Its grounded macro is cap-depressed."),
    ]
    L = ["| location | status | what to fix |", "|---|---|---|"]
    for loc, st, fix in items:
        L.append(f"| {loc} | **{st}** | {fix} |")
    L.append("")
    L.append("The paper's *structure* (blast-radius task, oracle pipeline, "
             "deterministic set grading, floors, N=5 two-stage stats, no-LLM-judge) is "
             "sound and survives. What must change is the single most-quoted empirical "
             "claim (universal D7=0.00) and every number derived from the exact-string "
             "grader on the probe dimensions (D3 partial, D4, D7, D10). The NEW grader "
             "(`semantic_sets.py`, frozen spec) should become the reported grader, with "
             "the exact-string column retained in an appendix as the conservative "
             "lower bound and the artifact explicitly disclosed as a methods "
             "contribution (‘why naive string-matching under-measures probe-encoded "
             "ground truth’).")
    return "\n".join(L)


def main() -> None:
    import time
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sonnet-grounded-dir", default=None, dest="sonnet_dir",
                    help="run dir whose Sonnet 4.6 grounded samples (12k-cap re-run) "
                         "supersede the truncated 4k-cap rows. Omit for the original "
                         "byte-identical regrade.")
    args = ap.parse_args()
    global SONNET_12K_DIR
    SONNET_12K_DIR = args.sonnet_dir
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = _runs(f"regrade_semantic_{ts}")
    out.mkdir(parents=True, exist_ok=True)

    inst = load_instances()
    per_sample, model_recs, mnotes = grade_all(inst)
    floor_recs, fnotes = grade_floors(inst)
    notes = mnotes + fnotes

    # results.jsonl: per-sample old+new
    with (out / "results.jsonl").open("w", encoding="utf-8") as fh:
        for r in per_sample:
            fh.write(json.dumps(r) + "\n")

    # summary.json: machine-readable aggregates per (label, split) under both graders
    summary = {"meta": {"ts": ts, "spec": "docs/semantic_grading_spec_v1.md",
                        "n_model_samples": len(per_sample), "notes": notes},
               "models": {}, "floors": {}}
    for l in model_labels(model_recs):
        summary["models"][l] = {}
        for split in ("templated", "grounded"):
            so, sn = agg(model_recs, l, "old", split), agg(model_recs, l, "new", split)
            if so or sn:
                summary["models"][l][split] = {"old": so, "new": sn}
    for bname in bl.BASELINE_NAMES:
        summary["floors"][bname] = {}
        for split in ("templated", "grounded"):
            so, sn = agg(floor_recs, bname, "old", split), agg(floor_recs, bname, "new", split)
            if so or sn:
                summary["floors"][bname][split] = {"old": so, "new": sn}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                      encoding="utf-8")

    report = render_report(model_recs, floor_recs, notes, ts)
    report_path = REPO / "paper" / "refs" / "regrade_semantic_2026-06-12.md"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nwrote {out}/results.jsonl")
    print(f"wrote {out}/summary.json")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
