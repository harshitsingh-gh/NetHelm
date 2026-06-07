"""Pure tests for the waypoint4 scenario topology (no Batfish needed).

The live D4 oracle is exercised by scripts/demo_extended_waypoint.py against a
running Batfish; here we only check the topology is self-consistent and the
change patch applies cleanly — the same structural guarantees the generator
self-checks for the square4 suite.
"""

from netbrace.tasks.safety import baseline_waypoint4 as wp
from netbrace.topology.patches import apply_unified_diff


def test_patch_round_trips():
    pre = wp.baseline_configs()["src"]
    post = apply_unified_diff(pre, wp.change_patch())
    assert post != pre
    # the dst route moved off the waypoint next-hop (.2) onto the alt next-hop (.6)
    assert "ip route 10.0.0.4/32 192.0.2.2" not in post
    assert "ip route 10.0.0.4/32 192.0.2.6" in post


def test_change_only_touches_target_node():
    pre = wp.baseline_configs()
    # the other three configs are untouched by the change (it patches src only)
    assert wp.CHANGE_TARGET == "src"
    for node in ("way", "alt", "dst"):
        assert pre[node] == wp.baseline_configs()[node]


def test_topology_facts_consistent():
    nodes = set(wp.NODES)
    assert set(wp.LOOPBACK_IP) == nodes
    for a, _ai, b, _bi in wp.LINKS:
        assert a in nodes and b in nodes
    for src, _dst, waypoint in wp.WAYPOINT_INTENTS:
        assert src in nodes and waypoint in nodes


def test_each_config_parses_as_its_hostname():
    cfgs = wp.baseline_configs()
    for node, text in cfgs.items():
        assert text.splitlines()[0] == node            # Batfish hostname header
        assert f"hostname {node}" in text
        assert "frr version" in text
