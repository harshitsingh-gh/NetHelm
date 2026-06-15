"""Scenario-level (two-stage) aggregation for the model sweep.

The adjudicator's binding ruling (paper/refs/fight_synthesis_2026-06-08.md, must-fix
#4): aggregate per-dimension P/R/F1 **AT THE SCENARIO LEVEL**, NOT pooled-i.i.d. The
N samples drawn for one (instance, model) are correlated (same prompt, same model,
temperature jitter) — pooling all N x instances as if independent understates the
variance and inflates significance. The correct two-stage estimator is:

  stage 1  per-instance statistic   = mean over the N samples for that instance
  stage 2  population statistic     = mean +/- std ACROSS the instance means

This module is pure arithmetic over ``ExtendedScoreRecord`` dumps (dicts) — no
Batfish, no API, no I/O — so it is unit-testable with synthetic records. It does NOT
re-implement P/R/F1 (the grader already did that per sample); it only does the
two-stage reduction, the split bucketing, and the false_session_alarm RATE.

NOT built (ruled overreach for HotNets): clustered/Bayesian bootstrap. Scenario-level
mean+/-std is the decided estimator.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import fmean, pstdev

from netbrace.graders.extended import SCORED_TYPES

# The two TRUTH-BEARING dimensions of a quiet-reroute BYPASS twin. Ground truth on a
# bypass is EXACTLY {D4 waypoint, D10 intent}; sessions/prefixes/reachability survive.
# Trap recall is recall-where-truth restricted to these two dims on bypass instances
# only — see ``reroute_detection_scores``.
REROUTE_TRUTH_DIMS = ("waypoint", "intent")


def _mean(xs: list[float]) -> float:
    return fmean(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    """Population std across instance means (stage-2 spread). 0.0 for a single
    instance (no cross-instance spread to report)."""
    return pstdev(xs) if len(xs) > 1 else 0.0


def _sem(xs: list[float]) -> float:
    """Standard error of the mean across instances = std / sqrt(n_instances)."""
    n = len(xs)
    if n <= 1:
        return 0.0
    return pstdev(xs) / math.sqrt(n)


def per_instance_means(
    sample_records: dict[str, list[dict]],
) -> dict[str, dict]:
    """Stage 1: collapse the N samples of each instance to that instance's MEAN.

    ``sample_records`` maps instance_id -> list of N ExtendedScoreRecord dicts (one
    per sample). Returns instance_id -> {per_dim_f1: {dim: mean_f1 over samples that
    had the dim active}, macro_f1, micro_f1, false_session_alarm_rate, invalid_rate}.

    A dimension contributes to an instance's per-dim mean only on samples where it is
    ACTIVE (non-empty in truth or prediction) — same active-type rule the grader uses
    to avoid vacuous 1.0s from empty-in-both dimensions.
    """
    out: dict[str, dict] = {}
    for inst_id, recs in sample_records.items():
        if not recs:
            continue
        dim_vals: dict[str, list[float]] = defaultdict(list)
        for r in recs:
            active = set(r.get("active_types") or [])
            for t, m in (r.get("per_type") or {}).items():
                if t in active:
                    dim_vals[t].append(float(m["f1"]))
        per_dim = {t: _mean(v) for t, v in dim_vals.items() if v}
        out[inst_id] = {
            "per_dim_f1": per_dim,
            "active_dims": sorted(per_dim),
            "macro_f1": _mean([float(r["macro_f1"]) for r in recs]),
            "micro_f1": _mean([float(r["micro_f1"]) for r in recs]),
            "false_session_alarm_rate": _mean(
                [1.0 if r.get("false_session_alarm") else 0.0 for r in recs]
            ),
            "invalid_rate": _mean(
                [0.0 if r.get("valid_prediction", True) else 1.0 for r in recs]
            ),
            "n_samples": len(recs),
        }
    return out


def population_stats(instance_means: dict[str, dict]) -> dict:
    """Stage 2: mean +/- std ACROSS instances (never pooled over samples).

    Input is the output of ``per_instance_means``. Returns the population report:
      { by_dimension: {dim: {mean_f1, std_f1, sem_f1, n_instances}},
        macro_f1: {mean,std,sem}, micro_f1: {...},
        false_session_alarm_rate: {mean,std,sem},
        invalid_rate: {mean,std,sem}, n_instances }
    Each per-dimension statistic is averaged only over the instances where that
    dimension was active (n_instances differs per dim — reported explicitly).
    """
    insts = list(instance_means.values())
    n = len(insts)

    by_dim: dict[str, dict] = {}
    for t in SCORED_TYPES:
        vals = [im["per_dim_f1"][t] for im in insts if t in im["per_dim_f1"]]
        if vals:
            by_dim[t] = {
                "mean_f1": round(_mean(vals), 6),
                "std_f1": round(_std(vals), 6),
                "sem_f1": round(_sem(vals), 6),
                "n_instances": len(vals),
            }

    def agg(key: str) -> dict:
        vals = [im[key] for im in insts]
        return {
            "mean": round(_mean(vals), 6),
            "std": round(_std(vals), 6),
            "sem": round(_sem(vals), 6),
        }

    return {
        "by_dimension": by_dim,
        "macro_f1": agg("macro_f1"),
        "micro_f1": agg("micro_f1"),
        "false_session_alarm_rate": agg("false_session_alarm_rate"),
        "invalid_rate": agg("invalid_rate"),
        "n_instances": n,
    }


def aggregate_scenario_level(sample_records: dict[str, list[dict]]) -> dict:
    """Full two-stage pipeline: stage-1 per-instance means then stage-2 population
    mean +/- std. This is the ONLY aggregation the sweep should use for the headline
    numbers (NOT pooling all N x instances as i.i.d.)."""
    return population_stats(per_instance_means(sample_records))


# =========================================================================== #
# REROUTE DETECTION METRIC (the non-gameable headline for the quiet-reroute split)
# --------------------------------------------------------------------------- #
# The macro_f1 / macro_f1_damage headline is GAMEABLE on the reroute split:
#   * "always-predict-{D4,D10}" scores macro_f1_damage = 1.000 because the damage-only
#     macro DROPS the gt_empty no_op twins, hiding every false alarm it commits there;
#   * "always-empty" / "diff-shape" all park at 0.50 on the full macro — no routing
#     reasoning required to pass half the calibration.
# The fix is a BALANCED-ACCURACY bypass-vs-no_op detector built from two label-pure
# channels (a recall measured ONLY on bypass twins; a false-alarm rate measured ONLY
# on no_op twins), so NO constant / label-independent predictor can clear 0.50 and
# Youden's J is pinned to 0 for any such predictor. See test_reroute_metric.py.
# =========================================================================== #


_REROUTE_FAMILY_NAMES: tuple[str, ...] | None = None


def _reroute_family_names() -> tuple[str, ...]:
    """The 13 reroute family names, LONGEST-first, cached. Derived from the
    authoritative ``scenarios.REROUTE_GENERATORS`` (lazy import — runtime only, so no
    import cycle). Empty tuple if unavailable (then the token fallback is used)."""
    global _REROUTE_FAMILY_NAMES
    if _REROUTE_FAMILY_NAMES is None:
        try:
            from netbrace.tasks.safety.scenarios import REROUTE_GENERATORS
            fams = [p[len("gen_"):].rstrip("_") for (_m, _f, p) in REROUTE_GENERATORS]
        except Exception:  # noqa: BLE001 — keep the metric importable without scenarios
            fams = []
        _REROUTE_FAMILY_NAMES = tuple(sorted(fams, key=len, reverse=True))
    return _REROUTE_FAMILY_NAMES


def reroute_family_of(instance_id: str) -> str:
    """Map an instance id ``gen_<family>_<dims_label>_s<seed>`` to its FAMILY.

    Matches against the 13 KNOWN reroute family names (longest-first), because the
    ``dims_label`` is NOT reliably hyphen-led — several generators use underscore-bearing
    knobs (``origin_code_alt_to_igp-bypass``, ``remove_dead_prepend_alt_inbound-bypass``,
    ``community_lp_rewrite_tag-bypass``), so a "first hyphen token" split would fold the
    knob into the family and shatter one family into several. Falls back to that token
    split only if no known family prefix matches.
    """
    body = instance_id
    if body.startswith("gen_"):
        body = body[len("gen_"):]
    # strip a trailing _s<digits> seed suffix
    if "_s" in body:
        head, tail = body.rsplit("_s", 1)
        if tail.isdigit():
            body = head
    for fam in _reroute_family_names():  # longest-first -> exact family, knob stripped
        if body == fam or body.startswith(fam + "_") or body.startswith(fam + "-"):
            return fam
    # Fallback: leading underscore-tokens up to the first hyphen-bearing token.
    fam_toks: list[str] = []
    for tok in body.split("_"):
        if "-" in tok:
            break
        fam_toks.append(tok)
    return "_".join(fam_toks) if fam_toks else body


def _record_family(rec: dict) -> str:
    """Family of a graded record. Prefers an explicit ``family`` field (cheap for the
    caller to attach); else derives it from ``instance``/``instance_id``/``task_id``.
    ``task_id`` is ``<instance_id>|<model>|<cond>|s<sample>`` so the leading ``|``-token
    is the instance id."""
    fam = rec.get("family")
    if fam:
        return str(fam)
    iid = rec.get("instance") or rec.get("instance_id")
    if not iid:
        tid = rec.get("task_id") or ""
        iid = tid.split("|", 1)[0] if tid else ""
    return reroute_family_of(str(iid)) if iid else "_unknown"


def _record_instance(rec: dict) -> str:
    """Instance id of a graded record (stage-1 grouping key)."""
    iid = rec.get("instance") or rec.get("instance_id")
    if iid:
        return str(iid)
    tid = rec.get("task_id") or ""
    return tid.split("|", 1)[0] if tid else "_unknown"


def _per_type(rec: dict) -> dict[str, dict]:
    return rec.get("per_type") or {}


def _recall_where_truth(rec: dict, dims: tuple[str, ...]) -> float | None:
    """recall-where-truth over ``dims`` for ONE graded sample.

    = mean over {d in dims : tp+fn > 0} of tp/(tp+fn). A dim with EMPTY truth
    (tp+fn == 0) is EXCLUDED — never averaged in as a vacuous 1.0 (memory
    grader_artifact_d7: an empty-truth dim returns recall 1.0). Returns None when no
    dim in ``dims`` carries any truth on this sample (so the caller can skip it rather
    than fold in a meaningless value). This is NOT the precision-dragged dimensional
    mean: precision/F1 are never read here.
    """
    pt = _per_type(rec)
    recalls: list[float] = []
    for d in dims:
        m = pt.get(d)
        if not m:
            continue
        tp = float(m.get("tp", 0))
        fn = float(m.get("fn", 0))
        if tp + fn > 0:
            recalls.append(tp / (tp + fn))
    return _mean(recalls) if recalls else None


def _pred_nonempty_over_scored(rec: dict) -> bool:
    """Does this prediction assert ANYTHING over the scored dimension types?

    The no_op false-alarm channel. A no_op twin's ground truth is COMPLETELY EMPTY, so
    any tp is impossible — a non-empty prediction is purely fp. PREFERS the grader's
    fixed ``empty_truth_false_alarm`` field (the authoritative, is_trap-independent
    calibration-twin FP signal restored by the bug fix); falls back to re-deriving from
    the per-type tp/fp footprint (tp+fp > 0 on any scored dim) for older records that
    predate the field. Both read the same grader-side arithmetic.
    """
    if "empty_truth_false_alarm" in rec:
        return bool(rec["empty_truth_false_alarm"])
    pt = _per_type(rec)
    for d in SCORED_TYPES:
        m = pt.get(d)
        if not m:
            continue
        if float(m.get("tp", 0)) + float(m.get("fp", 0)) > 0:
            return True
    return False


def _is_trap(rec: dict) -> bool:
    return bool(rec.get("is_trap", False))


def _bootstrap_ci(
    values: list[float], *, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI of the MEAN of ``values`` (resampling the values, which
    here are per-family statistics — the stage-2 unit). Deterministic given ``seed``.
    Degenerate inputs (0 or 1 value, or no spread) return (mean, mean)."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    m = _mean(values)
    if n == 1 or _std(values) == 0.0:
        return (m, m)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(fmean(resample))
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)


def _two_stage_family_pool(
    per_family_instance_values: dict[str, dict[str, list[float]]],
) -> dict:
    """Two-stage reduction of a per-family, per-instance bag of sample values.

    stage 1  per-instance statistic = mean over the N samples of that instance
    stage 2a per-family statistic   = mean over its instance means
    stage 2b headline               = mean over the per-family statistics (POOLED across
                                       families by EQUAL family weight), +/- SEM and a
                                       percentile bootstrap CI across families.

    Mirrors the existing scenario-level estimator's discipline (never pool raw samples
    i.i.d.). Returns {pooled, ci_lo, ci_hi, sem, n_families, by_family:{fam:{mean,
    n_instances}}}.
    """
    family_means: list[float] = []
    by_family: dict[str, dict] = {}
    for fam in sorted(per_family_instance_values):
        inst_map = per_family_instance_values[fam]
        inst_means = [_mean(v) for v in inst_map.values() if v]
        if not inst_means:
            continue
        fam_mean = _mean(inst_means)
        family_means.append(fam_mean)
        by_family[fam] = {
            "mean": round(fam_mean, 6),
            "n_instances": len(inst_means),
        }
    pooled = _mean(family_means)
    lo, hi = _bootstrap_ci(family_means)
    return {
        "pooled": round(pooled, 6),
        "ci_lo": round(lo, 6),
        "ci_hi": round(hi, 6),
        "sem": round(_sem(family_means), 6),
        "n_families": len(family_means),
        "by_family": by_family,
    }


def reroute_detection_scores(
    records: list[dict],
    *,
    truth_dims: tuple[str, ...] = REROUTE_TRUTH_DIMS,
) -> dict:
    """The NON-GAMEABLE reroute headline: a balanced bypass-vs-no_op detector.

    ``records`` is a flat list of graded sample dumps (``ExtendedScoreRecord.model_dump``
    rows, optionally carrying ``instance``/``family``/``gt_empty`` the sweep attaches),
    GRADED UNDER THE SEMANTIC GRADER, drawn from the quiet-reroute families (both the
    is_trap=True bypass twins AND the is_trap=False no_op calibration twins). Records
    from non-reroute scenarios should not be passed in; this function does not filter by
    scenario kind — the caller selects the reroute slice.

    Returns ``{trap_recall, no_op_far, netbrace_detect, youden_j, n_bypass, n_noop,
    per_family, detail}`` where the four scalars are the POOLED (equal-family-weight)
    headline and ``per_family`` is the diagnostic breakdown.

    Definitions (each channel is LABEL-PURE — measured on one twin class only):
      1. TRAP RECALL  — recall-where-truth over ``truth_dims`` ({D4,D10}), averaged ONLY
         over is_trap=True (bypass) instances. recall-where-truth excludes empty-truth
         dims, so it is NOT the precision-dragged dimensional mean and cannot be inflated
         by an empty-in-both dimension.
      2. NO_OP FALSE-ALARM RATE (FAR) — fraction of is_trap=False (no_op, empty-truth)
         instances whose prediction is NON-EMPTY over the scored dimension types =
         FP/(TN+FP).
      3. NETBRACE-DETECT = (trap_recall + (1 - no_op_far)) / 2 — balanced accuracy of the
         detector. A constant / label-independent predictor is pinned to 0.50 BY
         CONSTRUCTION regardless of the bypass:no_op ratio.
      4. YOUDEN_J = trap_recall - no_op_far — 0 for any constant / label-independent
         predictor; > 0 only with genuine bypass-vs-no_op discrimination.

    Aggregation is two-stage like the scenario-level estimator (per-instance mean over
    its N samples, then per-family mean over instance means), POOLED across reroute
    families by equal family weight for the headline. n_bypass / n_noop are INSTANCE
    counts (the stage-2 unit), not sample counts.
    """
    # bucket: channel -> family -> instance_id -> list of per-sample values
    recall_b: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    far_b: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for rec in records:
        fam = _record_family(rec)
        inst = _record_instance(rec)
        if _is_trap(rec):
            rwt = _recall_where_truth(rec, truth_dims)
            if rwt is not None:
                recall_b[fam][inst].append(rwt)
        else:
            far_b[fam][inst].append(1.0 if _pred_nonempty_over_scored(rec) else 0.0)

    trap = _two_stage_family_pool(recall_b)
    far = _two_stage_family_pool(far_b)

    trap_recall = trap["pooled"]
    no_op_far = far["pooled"]
    netbrace_detect = round((trap_recall + (1.0 - no_op_far)) / 2.0, 6)
    youden_j = round(trap_recall - no_op_far, 6)

    n_bypass = sum(len(m) for m in recall_b.values())
    n_noop = sum(len(m) for m in far_b.values())

    # per-family diagnostic: detect + J where BOTH channels have an instance.
    per_family: dict[str, dict] = {}
    fams = set(trap["by_family"]) | set(far["by_family"])
    for fam in sorted(fams):
        tr = trap["by_family"].get(fam, {}).get("mean")
        fr = far["by_family"].get(fam, {}).get("mean")
        entry: dict = {
            "trap_recall": tr,
            "no_op_far": fr,
            "n_bypass": len(recall_b.get(fam, {})),
            "n_noop": len(far_b.get(fam, {})),
        }
        if tr is not None and fr is not None:
            entry["netbrace_detect"] = round((tr + (1.0 - fr)) / 2.0, 6)
            entry["youden_j"] = round(tr - fr, 6)
        per_family[fam] = entry

    return {
        "trap_recall": trap_recall,
        "no_op_far": no_op_far,
        "netbrace_detect": netbrace_detect,
        "youden_j": youden_j,
        "n_bypass": n_bypass,
        "n_noop": n_noop,
        "per_family": per_family,
        "detail": {
            "trap_recall": {
                "pooled": trap["pooled"], "ci_lo": trap["ci_lo"],
                "ci_hi": trap["ci_hi"], "sem": trap["sem"],
                "n_families": trap["n_families"],
            },
            "no_op_far": {
                "pooled": far["pooled"], "ci_lo": far["ci_lo"],
                "ci_hi": far["ci_hi"], "sem": far["sem"],
                "n_families": far["n_families"],
            },
        },
    }
