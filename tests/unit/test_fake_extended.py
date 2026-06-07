"""Tests for ExtendedFakeModel and the flat serializer (round-trips the parser)."""

from netbrace.core.dimensions import (
    ExtendedBlastRadius,
    ForwardingAnomaly,
    RedundancyLoss,
    WaypointViolation,
)
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel


def _truth():
    return ExtendedBlastRadius(
        waypoint_violations=[WaypointViolation(src_node="src", dst_prefix="10.0.0.4/32", waypoint="way")],
        redundancy_losses=[RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24", before_paths=4, after_paths=2)],
        forwarding_anomalies=[ForwardingAnomaly(node="r1", dst_prefix="10.0.0.9/32", kind="loop")],
    )


def test_oracle_mode_round_trips_to_exact_pass():
    truth = _truth()
    text = ExtendedFakeModel("oracle").respond(truth)
    pred = parse_extended_prediction(text)
    sr = grade_extended(pred, truth, task_id="t")
    assert sr.status == "pass"
    assert sr.exact_match is True


def test_empty_mode_misses_everything():
    truth = _truth()
    pred = parse_extended_prediction(ExtendedFakeModel("empty").respond(truth))
    sr = grade_extended(pred, truth, task_id="t")
    assert sr.status == "fail"
    assert sr.macro_f1 == 0.0


def test_garbage_mode_is_invalid():
    pred = parse_extended_prediction(ExtendedFakeModel("garbage").respond(_truth()))
    assert pred is None
    sr = grade_extended(pred, _truth(), task_id="t")
    assert sr.status == "invalid"


def test_bad_mode_rejected():
    try:
        ExtendedFakeModel("wishful")
        assert False, "expected ValueError"
    except ValueError:
        pass
