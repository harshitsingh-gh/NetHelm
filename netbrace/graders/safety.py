"""The blast-radius grader: compares a model prediction against ground truth.

This is the load-bearing scoring logic. It is pure (no I/O) and fully tested.

Inputs:
  * prediction: a BlastRadius (already parsed from model output; may be None if
    the model output could not be parsed at all -> scored as `invalid`).
  * ground_truth: the oracle's BlastRadius.
  * valid_topology_nodes / valid_prefixes: used to count hallucinated references
    (predicted elements naming things that don't exist). These do NOT change the
    set score — a hallucinated element simply lands in `fp` like any wrong guess —
    but we report the count separately for the failure-mode analysis.

Output: a ScoreRecord (see core.schemas).
"""

from __future__ import annotations

from typing import Optional

from netbrace.core.schemas import (
    BlastRadius,
    ELEMENT_TYPES,
    ScoreRecord,
    TypeMetrics,
)
from netbrace.graders.sets import SetScore, macro_f1, micro_f1, score_sets

PASS_F1_THRESHOLD = 0.80


def _count_hallucinations(
    prediction: BlastRadius,
    valid_nodes: Optional[set[str]],
    valid_prefixes: Optional[set[str]],
) -> int:
    if valid_nodes is None and valid_prefixes is None:
        return 0
    n = 0
    vn = valid_nodes or set()
    vp = valid_prefixes or set()
    for e in prediction.sessions_lost:
        if valid_nodes is not None and e.node not in vn:
            n += 1
    for e in prediction.prefixes_lost:
        if valid_nodes is not None and e.node not in vn:
            n += 1
        elif valid_prefixes is not None and e.prefix not in vp:
            n += 1
    for e in prediction.reachability_lost:
        if valid_nodes is not None and e.src_node not in vn:
            n += 1
        elif valid_prefixes is not None and e.dst_prefix not in vp:
            n += 1
    return n


def grade(
    prediction: Optional[BlastRadius],
    ground_truth: BlastRadius,
    *,
    is_trap: bool = False,
    valid_nodes: Optional[set[str]] = None,
    valid_prefixes: Optional[set[str]] = None,
    task_id: str = "",
) -> ScoreRecord:
    """Grade one prediction. ``prediction is None`` means unparseable output."""
    # ---- invalid: could not parse the model output at all ----
    if prediction is None:
        return ScoreRecord(
            task_id=task_id,
            status="invalid",
            valid_prediction=False,
            is_trap=is_trap,
            macro_f1=0.0,
            micro_f1=0.0,
            exact_match=False,
        )

    pred = prediction.normalized()
    truth = ground_truth.normalized()
    pred_keys = pred.key_sets()
    truth_keys = truth.key_sets()

    per_type: dict[str, TypeMetrics] = {}
    set_scores: list[SetScore] = []
    active_f1s: list[float] = []  # only types non-empty in truth OR prediction
    for t in ELEMENT_TYPES:
        s = score_sets(pred_keys[t], truth_keys[t])
        set_scores.append(s)
        per_type[t] = TypeMetrics(
            tp=s.tp, fp=s.fp, fn=s.fn,
            precision=s.precision, recall=s.recall, f1=s.f1,
        )
        if pred_keys[t] or truth_keys[t]:
            active_f1s.append(s.f1)

    # Macro over active types only -> a type empty in both does not inflate the
    # score with a vacuous 1.0. No active types == correct "nothing breaks" == 1.0.
    macro = macro_f1(active_f1s) if active_f1s else 1.0
    micro = micro_f1(set_scores)
    exact = pred_keys == truth_keys

    truth_empty = truth.is_empty()
    pred_empty = pred.is_empty()
    false_alarm = is_trap and truth_empty and not pred_empty

    # ---- status ladder (plan.md §6) ----
    if exact:
        status = "pass"
    elif macro >= PASS_F1_THRESHOLD:
        status = "pass"
    elif macro > 0.0:
        status = "partial"
    else:
        status = "fail"

    return ScoreRecord(
        task_id=task_id,
        status=status,
        valid_prediction=True,
        is_trap=is_trap,
        false_alarm=false_alarm,
        per_type=per_type,
        macro_f1=macro,
        micro_f1=micro,
        exact_match=exact,
        hallucinated_refs=_count_hallucinations(pred, valid_nodes, valid_prefixes),
    )
