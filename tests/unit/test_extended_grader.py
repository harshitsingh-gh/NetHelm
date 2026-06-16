"""Tests for the extended 8-dimension grader."""

import math

from netbrace.core.dimensions import (
    ExtendedBlastRadius,
    FilterDelta,
    ForwardingAnomaly,
    RedundancyLoss,
    WaypointViolation,
)
from netbrace.core.schemas import BlastRadius, SessionLost
from netbrace.graders.extended import grade_extended


def _truth():
    """A blast radius that spans four dimensions (D1 + D4 + D5 + D7)."""
    return ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")]),
        waypoint_violations=[
            WaypointViolation(src_node="r1", dst_prefix="10.0.0.5/32", waypoint="fw1")
        ],
        redundancy_losses=[RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24")],
        forwarding_anomalies=[
            ForwardingAnomaly(node="r3", dst_prefix="10.0.0.9/32", kind="blackhole")
        ],
    )


def test_exact_match_is_pass_across_dimensions():
    sr = grade_extended(_truth(), _truth(), task_id="t")
    assert sr.status == "pass"
    assert sr.exact_match is True
    assert sr.macro_f1 == 1.0
    # only the four populated types are "active"; empty-in-both types excluded
    assert set(sr.active_types) == {"sessions", "waypoint", "redundancy", "forwarding"}


def test_missing_one_dimension_is_partial():
    # Predict everything except the forwarding anomaly -> 3 of 4 active types perfect.
    pred = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")]),
        waypoint_violations=[
            WaypointViolation(src_node="r1", dst_prefix="10.0.0.5/32", waypoint="fw1")
        ],
        redundancy_losses=[RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24")],
    )
    sr = grade_extended(pred, _truth(), task_id="t")
    assert sr.status == "partial"
    assert not sr.exact_match
    # 3 active types f1=1, forwarding f1=0 -> macro 3/4
    assert math.isclose(sr.macro_f1, 0.75, rel_tol=1e-9)


def test_false_session_alarm_fires_when_session_predicted_but_truth_has_none():
    # The documented LLM trap: truth has NO session loss (e.g. an attribute change),
    # but the model predicts a session drop. Must flag false_session_alarm.
    truth = ExtendedBlastRadius(
        waypoint_violations=[
            WaypointViolation(src_node="src", dst_prefix="203.0.113.0/24", waypoint="way")
        ]
    )  # D4 only; sessions = ∅
    pred = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="alt", peer_ip="0.0.0.0")])
    )
    sr = grade_extended(pred, truth, is_trap=True, task_id="t")
    assert sr.false_session_alarm is True
    assert sr.macro_f1 < 0.5  # naive "session drops" reflex scores poorly


def test_no_false_session_alarm_when_truth_has_a_session():
    # When sessions genuinely drop, predicting them is correct, not a false alarm.
    truth = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    )
    pred = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    )
    sr = grade_extended(pred, truth, task_id="t")
    assert sr.false_session_alarm is False


def test_filter_d6_is_deferred_not_scored():
    # D6 (filter) is DEFERRED in v1: Batfish cannot ground it on FRR (needs a
    # vendor-config snapshot), so the grader excludes "filter" from SCORED_TYPES.
    # A filter-only prediction must NOT be scored/penalised against an ungroundable
    # truth — 'filter' must not appear in per_type or active_types.
    truth = ExtendedBlastRadius()  # the oracle never grounds filter in v1
    pred = ExtendedBlastRadius(
        filter_deltas=[FilterDelta(
            node="fw", src_ip="10.0.0.1", dst_ip="10.0.0.2",
            transition="deny_to_permit", protocol="tcp", dst_port=443,
        )]
    )
    sr = grade_extended(pred, truth, task_id="t")
    assert "filter" not in sr.per_type
    assert "filter" not in sr.active_types


def test_none_prediction_is_invalid():
    sr = grade_extended(None, _truth(), task_id="t")
    assert sr.status == "invalid"
    assert sr.valid_prediction is False
    assert sr.macro_f1 == 0.0


def test_trap_correct_no_impact_is_pass():
    sr = grade_extended(ExtendedBlastRadius(), ExtendedBlastRadius(), is_trap=True, task_id="t")
    assert sr.status == "pass"
    assert sr.false_alarm is False
    assert sr.macro_f1 == 1.0
    assert sr.active_types == []


def test_trap_false_alarm_flagged_on_new_dimension():
    # A trap whose only predicted impact is a (wrong) redundancy loss.
    pred = ExtendedBlastRadius(redundancy_losses=[RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24")])
    sr = grade_extended(pred, ExtendedBlastRadius(), is_trap=True, task_id="t")
    assert sr.false_alarm is True
    assert sr.status == "fail"


def test_micro_pools_across_dimensions():
    # Truth has 2 elements (1 session + 1 waypoint); pred gets the session only.
    truth = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")]),
        waypoint_violations=[WaypointViolation(src_node="r1", dst_prefix="10.0.0.5/32", waypoint="fw")],
    )
    pred = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")]),
    )
    sr = grade_extended(pred, truth, task_id="t")
    # pooled tp=1 fp=0 fn=1 -> precision 1, recall 0.5 -> micro f1 = 2/3
    assert math.isclose(sr.micro_f1, 2 / 3, rel_tol=1e-9)
