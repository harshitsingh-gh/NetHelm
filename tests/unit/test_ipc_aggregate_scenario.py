"""Structural tests for ipc_aggregate (Class-1 #4) — no Batfish required."""
from __future__ import annotations

from netbrace.tasks.safety import scenarios
from netbrace.tasks.safety import baseline_ipc_aggregate as agg
from netbrace.topology.patches import apply_unified_diff


def test_registered():
    assert "ipc_aggregate" in scenarios.REGISTRY


def test_builds_with_three_nodes():
    scn = scenarios.build("ipc_aggregate")
    assert scn.change_target == "r1"
    assert set(scn.nodes) == {"r1", "r2", "r3"}


def test_patch_round_trips_on_r1_only():
    scn = scenarios.build("ipc_aggregate")
    pre = scn.pre_configs
    post = scn.post_configs()
    changed = [n for n in scn.nodes if post[n] != pre[n]]
    assert changed == ["r1"]
    assert apply_unified_diff(pre["r1"], scn.patch) == post["r1"]


def test_post_r1_permits_aggregate_and_attaches_routemap():
    post_r1 = scenarios.build("ipc_aggregate").post_configs()["r1"]
    # the /24 aggregate is permitted EXACTLY (no `le` — so /25s do not match)
    assert "ip prefix-list CLEANUP_OUT seq 5 permit 203.0.113.0/24" in post_r1
    # the route-map is attached outbound toward r2
    assert "neighbor 10.0.0.2 route-map TO_R2_OUT out" in post_r1
    # the prefix-list exists and the more-specifics are NOT explicitly permitted
    assert "ip prefix-list CLEANUP_OUT" in post_r1
    assert "permit 203.0.113.0/25" not in post_r1
    assert "permit 203.0.113.128/25" not in post_r1


def test_baseline_origin_advertises_aggregate_and_both_specifics():
    r3 = agg.baseline_configs()["r3"]
    assert "network 203.0.113.0/24" in r3
    assert "network 203.0.113.0/25" in r3
    assert "network 203.0.113.128/25" in r3
    # the aggregate is backed by a discard static (so `network /24` originates)
    assert "ip route 203.0.113.0/24 Null0" in r3


def test_probes_well_formed_with_controls():
    scn = scenarios.build("ipc_aggregate")
    srcs = {s for (s, _d) in scn.reachability_flows}
    # r2 is the affected client; r1/r3 are negative-control sources
    assert "r2" in srcs
    assert {"r1", "r3"} <= srcs
    # watched: aggregate + both /25s + three loopbacks (no static backup => no D2
    # false-negative masking, but loopbacks/aggregate are negative controls)
    assert agg.AGGREGATE_PREFIX in scn.watched_prefixes
    assert agg.SPECIFIC_LOW in scn.watched_prefixes
    assert agg.SPECIFIC_HIGH in scn.watched_prefixes
    assert sum(p.endswith("/32") for p in scn.watched_prefixes) == 3
