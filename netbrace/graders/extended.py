"""Grader for the extended (8-dimension) blast radius.

Same contract and status ladder as ``graders/safety.grade``, but scores all eight
element types (D1-D8) carried by ``core.dimensions.ExtendedBlastRadius``. It
REUSES the frozen pure arithmetic in ``graders/sets.py`` — it does not
re-implement precision/recall/F1 — so the v0 and extended graders agree exactly
on the three shared types.

Output is an ``ExtendedScoreRecord``: per-type metrics over the 8 types plus the
macro/micro/exact/false-alarm summary.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from netbrace.core.dimensions import EXT_ELEMENT_TYPES, ExtendedBlastRadius
from netbrace.core.schemas import TypeMetrics
from netbrace.graders.sets import SetScore, macro_f1, micro_f1, score_sets

PASS_F1_THRESHOLD = 0.80

ScoreStatus = Literal["pass", "partial", "fail", "invalid", "error"]


class ExtendedScoreRecord(BaseModel):
    """Grading output for one extended-blast-radius prediction (8 dimensions)."""

    schema_version: Literal["nethelm.score_ext.v0"] = "nethelm.score_ext.v0"
    task_id: str
    status: ScoreStatus
    valid_prediction: bool = True
    is_trap: bool = False
    false_alarm: bool = False
    per_type: dict[str, TypeMetrics] = Field(default_factory=dict)
    macro_f1: float = 0.0
    micro_f1: float = 0.0
    exact_match: bool = False
    active_types: list[str] = Field(default_factory=list)


def grade_extended(
    prediction: Optional[ExtendedBlastRadius],
    ground_truth: ExtendedBlastRadius,
    *,
    is_trap: bool = False,
    task_id: str = "",
) -> ExtendedScoreRecord:
    """Grade one extended prediction. ``prediction is None`` => unparseable output."""
    # ---- invalid: could not parse the model output at all ----
    if prediction is None:
        return ExtendedScoreRecord(
            task_id=task_id,
            status="invalid",
            valid_prediction=False,
            is_trap=is_trap,
            macro_f1=0.0,
            micro_f1=0.0,
            exact_match=False,
        )

    pred_keys = prediction.normalized().key_sets()
    truth_keys = ground_truth.normalized().key_sets()

    per_type: dict[str, TypeMetrics] = {}
    set_scores: list[SetScore] = []
    active_f1s: list[float] = []
    active_types: list[str] = []
    for t in EXT_ELEMENT_TYPES:
        s = score_sets(pred_keys[t], truth_keys[t])
        set_scores.append(s)
        per_type[t] = TypeMetrics(
            tp=s.tp, fp=s.fp, fn=s.fn,
            precision=s.precision, recall=s.recall, f1=s.f1,
        )
        # A type empty in both truth and prediction is excluded from the macro
        # average so it cannot inflate the score with a vacuous 1.0.
        if pred_keys[t] or truth_keys[t]:
            active_f1s.append(s.f1)
            active_types.append(t)

    macro = macro_f1(active_f1s) if active_f1s else 1.0
    micro = micro_f1(set_scores)
    exact = pred_keys == truth_keys

    truth_empty = ground_truth.is_empty()
    pred_empty = prediction.is_empty()
    false_alarm = is_trap and truth_empty and not pred_empty

    # ---- status ladder (identical to safety.grade) ----
    if exact:
        status: ScoreStatus = "pass"
    elif macro >= PASS_F1_THRESHOLD:
        status = "pass"
    elif macro > 0.0:
        status = "partial"
    else:
        status = "fail"

    return ExtendedScoreRecord(
        task_id=task_id,
        status=status,
        valid_prediction=True,
        is_trap=is_trap,
        false_alarm=false_alarm,
        per_type=per_type,
        macro_f1=macro,
        micro_f1=micro,
        exact_match=exact,
        active_types=active_types,
    )
