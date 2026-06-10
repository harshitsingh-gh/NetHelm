"""Tests for the extended blast-radius dimensions (D4-D8) and ExtendedBlastRadius."""

from netbrace.core.dimensions import (
    EXT_ELEMENT_TYPES,
    ExtendedBlastRadius,
    FilterDelta,
    ForwardingAnomaly,
    RedundancyLoss,
    ScaleViolation,
    WaypointViolation,
)
from netbrace.core.schemas import BlastRadius, SessionLost


# ----- element keys are deterministic + canonicalized -----
def test_waypoint_key_canonicalizes_node_and_prefix():
    a = WaypointViolation(src_node="R1", dst_prefix="10.0.0.5", waypoint="FW1")
    b = WaypointViolation(src_node="r1", dst_prefix="10.0.0.5/32", waypoint="fw1")
    assert a.key == b.key
    assert a.key == "waypoint|src=r1|dst=10.0.0.5/32|via=fw1|vrf=default"


def test_redundancy_key_ignores_path_counts():
    a = RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24", before_paths=4, after_paths=2)
    b = RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24", before_paths=4, after_paths=1)
    assert a.key == b.key  # magnitude is an attribute, not part of identity


def test_filter_delta_transition_is_part_of_key():
    permit_to_deny = FilterDelta(
        node="fw", src_ip="10.0.0.1", dst_ip="10.0.0.2",
        transition="permit_to_deny", protocol="TCP", dst_port=443,
    )
    deny_to_permit = FilterDelta(
        node="fw", src_ip="10.0.0.1", dst_ip="10.0.0.2",
        transition="deny_to_permit", protocol="tcp", dst_port=443,
    )
    assert permit_to_deny.key != deny_to_permit.key
    assert "proto=tcp" in permit_to_deny.key  # protocol lowercased
    assert "dport=443" in permit_to_deny.key


def test_filter_delta_wildcard_port():
    f = FilterDelta(node="fw", src_ip="10.0.0.1", dst_ip="10.0.0.2", transition="permit_to_deny")
    assert "dport=*" in f.key


def test_forwarding_and_scale_keys():
    fa = ForwardingAnomaly(node="r2", dst_prefix="10.0.0.9/32", kind="blackhole")
    assert fa.key == "anomaly|blackhole|node=r2|vrf=default|dst=10.0.0.9/32"
    sv = ScaleViolation(node="agg1", resource="fib", limit=16000, observed=18000)
    assert sv.key == "scale|node=agg1|resource=fib"


# ----- ExtendedBlastRadius surface -----
def test_ext_element_types_order():
    # The original 8 types are preserved as an ordered prefix; D9 bgp_withdrawn then
    # D10 intent are each appended at the end (additive — no prior index shifts).
    assert EXT_ELEMENT_TYPES == (
        "sessions", "prefixes", "reachability",
        "waypoint", "redundancy", "filter", "forwarding", "scale",
        "bgp_withdrawn", "intent",
    )


def test_key_sets_spans_eight_types():
    ext = ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")]),
        waypoint_violations=[WaypointViolation(src_node="r1", dst_prefix="10.0.0.5", waypoint="fw")],
    )
    ks = ext.key_sets()
    assert set(ks.keys()) == set(EXT_ELEMENT_TYPES)
    assert len(ks["sessions"]) == 1
    assert len(ks["waypoint"]) == 1
    assert ks["scale"] == set()


def test_normalized_dedupes_and_sorts():
    dup = RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24")
    ext = ExtendedBlastRadius(redundancy_losses=[dup, dup])
    norm = ext.normalized()
    assert len(norm.redundancy_losses) == 1


def test_is_empty():
    assert ExtendedBlastRadius().is_empty()
    assert not ExtendedBlastRadius(
        scale_violations=[ScaleViolation(node="r1", resource="rib")]
    ).is_empty()
    # non-empty base also counts as non-empty
    assert not ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    ).is_empty()
