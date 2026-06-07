"""Tests for the set metrics and the safety grader (the correctness core)."""

import math

from netbrace.core.schemas import (
    BlastRadius,
    PrefixLost,
    SessionLost,
)
from netbrace.graders.safety import grade
from netbrace.graders.sets import macro_f1, micro_f1, score_sets


# ----- pure set metrics -----
def test_score_sets_exact_match():
    s = score_sets({"a", "b"}, {"a", "b"})
    assert (s.tp, s.fp, s.fn) == (2, 0, 0)
    assert s.f1 == 1.0


def test_score_sets_missing_prediction_hurts_recall():
    s = score_sets({"a"}, {"a", "b"})
    assert (s.tp, s.fp, s.fn) == (1, 0, 1)
    assert s.precision == 1.0
    assert s.recall == 0.5
    assert math.isclose(s.f1, 2 / 3, rel_tol=1e-9)


def test_score_sets_extra_prediction_hurts_precision():
    s = score_sets({"a", "b"}, {"a"})
    assert (s.tp, s.fp, s.fn) == (1, 1, 0)
    assert s.recall == 1.0
    assert s.precision == 0.5


def test_score_sets_empty_empty_is_perfect():
    s = score_sets(set(), set())
    assert (s.precision, s.recall, s.f1) == (1.0, 1.0, 1.0)


def test_score_sets_false_alarm():
    s = score_sets({"a"}, set())  # predicted impact where there is none
    assert s.precision == 0.0
    assert s.recall == 1.0
    assert s.f1 == 0.0


def test_micro_f1_pools_counts():
    s1 = score_sets({"a"}, {"a", "b"})   # tp1 fn1
    s2 = score_sets({"c"}, {"c"})        # tp1
    # pooled tp=2 fp=0 fn=1 -> p=1 r=2/3 f1=0.8
    assert math.isclose(micro_f1([s1, s2]), 0.8, rel_tol=1e-9)


def test_macro_f1_is_mean():
    assert macro_f1([1.0, 0.0, 0.5]) == 0.5
    assert macro_f1([]) == 0.0


# ----- the grader -----
def _truth():
    return BlastRadius(
        sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")],
        prefixes_lost=[PrefixLost(node="r3", prefix="10.0.0.2/32")],
    )


def test_grade_exact_is_pass():
    sr = grade(_truth(), _truth(), task_id="t")
    assert sr.status == "pass"
    assert sr.exact_match is True
    assert sr.macro_f1 == 1.0


def test_grade_partial_is_partial():
    pred = BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    sr = grade(pred, _truth(), task_id="t")
    # sessions f1=1, prefixes f1=0, reachability empty/empty=1 -> macro 2/3
    assert sr.status == "partial"
    assert not sr.exact_match
    assert 0.0 < sr.macro_f1 < 0.8


def test_grade_none_prediction_is_invalid():
    sr = grade(None, _truth(), task_id="t")
    assert sr.status == "invalid"
    assert sr.valid_prediction is False
    assert sr.macro_f1 == 0.0


def test_grade_trap_correct_no_impact_is_pass():
    sr = grade(BlastRadius(), BlastRadius(), is_trap=True, task_id="t")
    assert sr.status == "pass"
    assert sr.false_alarm is False
    assert sr.macro_f1 == 1.0


def test_grade_trap_false_alarm_flagged():
    pred = BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    sr = grade(pred, BlastRadius(), is_trap=True, task_id="t")
    assert sr.false_alarm is True
    assert sr.status == "fail"  # macro_f1 == 0 with valid output


def test_grade_counts_hallucinated_refs():
    pred = BlastRadius(sessions_lost=[SessionLost(node="r9", peer_ip="10.0.0.2")])
    sr = grade(pred, _truth(), valid_nodes={"r1", "r2", "r3"}, task_id="t")
    assert sr.hallucinated_refs == 1
