"""Pure set-comparison metrics. No networking, no I/O — just arithmetic.

This module is deliberately tiny and total. Every branch is unit-tested. If you
change anything here, run `pytest tests/unit/test_grader.py` and keep it green.

Vacuous-truth convention (plan.md §6):
  precision = 1.0 when nothing was predicted (all 0 predictions were "correct")
  recall    = 1.0 when nothing was expected  (found all 0 true items)
This makes the edge cases fall out without special-casing:
  predicted empty AND expected empty  -> p=1, r=1, f1=1   (correct "no impact")
  predicted non-empty, expected empty -> p=0, r=1, f1=0   (false alarm)
  predicted empty, expected non-empty -> p=1, r=0, f1=0   (total miss)

NOTE: the *task-level* macro average (in graders/safety.py) only averages over
element-types that are active (non-empty in truth or prediction), so a type that
is empty in both does not inflate the score with a vacuous 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetScore:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def score_sets(predicted: set[str], expected: set[str]) -> SetScore:
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)

    # Vacuous truth: empty predicted -> precision 1.0; empty expected -> recall 1.0.
    precision = tp / (tp + fp) if predicted else 1.0
    recall = tp / (tp + fn) if expected else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return SetScore(tp, fp, fn, precision, recall, f1)


def macro_f1(per_type_f1: list[float]) -> float:
    """Mean of per-type F1s. Empty input -> 0.0."""
    return sum(per_type_f1) / len(per_type_f1) if per_type_f1 else 0.0


def micro_f1(scores: list[SetScore]) -> float:
    """F1 over pooled TP/FP/FN across all types."""
    tp = sum(s.tp for s in scores)
    fp = sum(s.fp for s in scores)
    fn = sum(s.fn for s in scores)
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0  # all types were empty/empty
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
