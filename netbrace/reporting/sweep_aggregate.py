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
from collections import defaultdict
from statistics import fmean, pstdev

from netbrace.graders.extended import SCORED_TYPES


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
