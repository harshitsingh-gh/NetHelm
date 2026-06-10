"""Structural tests for S-IPC-02 (ipc_fanout) — no Batfish required."""
from __future__ import annotations

from netbrace.tasks.safety import scenarios
from netbrace.tasks.safety import scenario_ipc_fanout as fan
from netbrace.topology.patches import apply_unified_diff


def test_registered():
    assert "ipc_fanout" in scenarios.REGISTRY


def test_builds_with_five_nodes_rr():
    scn = scenarios.build("ipc_fanout")
    assert scn.change_target == "r1"
    assert set(scn.nodes) == {"r1", "r2", "r3", "r4", "r5"}


def test_patch_round_trips_on_r1_only():
    scn = scenarios.build("ipc_fanout")
    pre = scn.pre_configs
    post = scn.post_configs()
    # only r1 changes
    changed = [n for n in scn.nodes if post[n] != pre[n]]
    assert changed == ["r1"]
    # patch applies cleanly
    assert apply_unified_diff(pre["r1"], scn.patch) == post["r1"]


def test_post_attaches_routemap_to_three_clients():
    post_r1 = scenarios.build("ipc_fanout").post_configs()["r1"]
    for nbr in ("10.0.0.2", "10.0.0.3", "10.0.0.4"):
        assert f"neighbor {nbr} route-map TO_CLIENTS_OUT out" in post_r1
    # r5 (origin/transit) is NOT filtered
    assert "neighbor 10.0.0.5 route-map TO_CLIENTS_OUT out" not in post_r1
    assert "ip prefix-list CLEANUP_OUT" in post_r1


def test_probes_cover_lost_clients_and_controls():
    scn = scenarios.build("ipc_fanout")
    srcs = {s for (s, _d) in scn.reachability_flows}
    # the three leaf clients that lose the prefix + the two negative controls
    assert {"r2", "r3", "r4"} <= srcs
    assert {"r1", "r5"} <= srcs
    # customer prefix + all five loopbacks are watched (loopbacks = neg controls)
    assert fan.CUSTOMER_PREFIX in scn.watched_prefixes
    assert sum(p.endswith("/32") for p in scn.watched_prefixes) == 5
