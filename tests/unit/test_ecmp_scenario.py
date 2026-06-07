"""Pure tests for the ecmp4 (D5 redundancy) scenario (no Batfish needed)."""

from netbrace.tasks.safety import baseline_ecmp4 as ec
from netbrace.topology.patches import apply_unified_diff


def test_patch_removes_one_of_two_ecmp_routes():
    pre = ec.baseline_configs()["src"]
    post = apply_unified_diff(pre, ec.change_patch())
    # both ECMP next-hops present before; only the m1 path survives after
    assert pre.count("ip route 10.0.0.4/32") == 2
    assert post.count("ip route 10.0.0.4/32") == 1
    assert "ip route 10.0.0.4/32 192.0.2.2" in post
    assert "ip route 10.0.0.4/32 192.0.2.6" not in post


def test_topology_facts_consistent():
    nodes = set(ec.NODES)
    assert set(ec.LOOPBACK_IP) == nodes
    for a, _ai, b, _bi in ec.LINKS:
        assert a in nodes and b in nodes
    for node, prefix in ec.REDUNDANCY_TARGETS:
        assert node in nodes and prefix.endswith("/32")
