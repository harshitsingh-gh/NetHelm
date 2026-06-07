"""Tests for the extended (8-dimension) tolerant parser."""

from netbrace.core.dimensions import ExtendedBlastRadius, ForwardingAnomaly, WaypointViolation
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended


def test_fenced_block_parses_all_new_dimensions():
    text = """Here is my analysis.
```json
{
  "sessions_lost": [],
  "waypoint_violations": [{"src_node": "src", "dst_prefix": "10.0.0.4/32", "waypoint": "way"}],
  "redundancy_losses": [{"node": "leaf1", "dst_prefix": "10.1.0.0/24", "before_paths": 4, "after_paths": 2}],
  "filter_deltas": [{"node": "fw", "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "protocol": "tcp", "dst_port": 443, "transition": "permit_to_deny"}],
  "forwarding_anomalies": [{"node": "r1", "dst_prefix": "10.0.0.4/32", "kind": "blackhole"}],
  "scale_violations": [{"node": "agg1", "resource": "fib", "limit": 16000, "observed": 18000}],
  "reasoning": "..."
}
```"""
    ext = parse_extended_prediction(text)
    ks = ext.key_sets()
    assert ks["waypoint"] == {"waypoint|src=src|dst=10.0.0.4/32|via=way|vrf=default"}
    assert ks["redundancy"] == {"redundancy|node=leaf1|vrf=default|prefix=10.1.0.0/24"}
    assert ks["forwarding"] == {"anomaly|blackhole|node=r1|vrf=default|dst=10.0.0.4/32"}
    assert len(ks["filter"]) == 1 and len(ks["scale"]) == 1


def test_bare_object_without_fence_parses():
    text = '{"forwarding_anomalies": [{"node": "r1", "dst_prefix": "10.0.0.4/32", "kind": "blackhole"}]}'
    ext = parse_extended_prediction(text)
    assert len(ext.forwarding_anomalies) == 1


def test_missing_keys_yield_empty_lists():
    ext = parse_extended_prediction('{"sessions_lost": []}')
    assert ext.is_empty()


def test_bad_enum_values_are_dropped_not_fatal():
    # kind="meltdown" is not a valid ForwardingAnomaly kind -> that element drops,
    # the valid one survives.
    text = """```json
{"forwarding_anomalies": [
  {"node": "r1", "dst_prefix": "10.0.0.4/32", "kind": "meltdown"},
  {"node": "r2", "dst_prefix": "10.0.0.5/32", "kind": "loop"}
]}
```"""
    ext = parse_extended_prediction(text)
    assert len(ext.forwarding_anomalies) == 1
    assert ext.forwarding_anomalies[0].kind == "loop"


def test_no_json_returns_none():
    assert parse_extended_prediction("I think nothing will break, honestly.") is None
    assert parse_extended_prediction("") is None


def test_full_model_text_to_grade_for_waypoint_scenario():
    """Simulates the real path: a model's text -> parse -> grade vs oracle truth."""
    truth = ExtendedBlastRadius(
        waypoint_violations=[WaypointViolation(src_node="src", dst_prefix="10.0.0.4/32", waypoint="way")]
    )
    model_text = """Looks like traffic will bypass the inspection node.
```json
{"waypoint_violations": [{"src_node": "src", "dst_prefix": "10.0.0.4/32", "waypoint": "way"}]}
```"""
    pred = parse_extended_prediction(model_text)
    sr = grade_extended(pred, truth, task_id="wp")
    assert sr.status == "pass"
    assert sr.exact_match is True


def test_full_model_text_to_grade_for_blackhole_scenario():
    truth = ExtendedBlastRadius(
        forwarding_anomalies=[ForwardingAnomaly(node="r1", dst_prefix="10.0.0.4/32", kind="blackhole")]
    )
    # A model that only reports reachability loss (D3) misses the D7 anomaly.
    naive_text = '{"reachability_lost": [{"src_node": "r1", "dst_prefix": "10.0.0.4/32"}]}'
    sr = grade_extended(parse_extended_prediction(naive_text), truth, task_id="bh")
    assert sr.status == "fail"  # forwarding dimension is all FN; reachability is all FP
