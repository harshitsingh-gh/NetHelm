"""Pure tests for S-IPC-01 (Class 1 — internal routing-policy collapse).

No Batfish needed: the live ground truth (D1=∅, D2/D3 on the customer prefix) is
verified by scripts/run_extended_scenario.py --scenario ipc. Here we lock the
patch round-trip, that filtering uses prefix-list/route-map ONLY (no FRR
access-list), and that the change adds exactly the intended objects to r1 only.
"""

from netbrace.tasks.safety import baseline_ipc3 as ipc
from netbrace.tasks.safety import scenario_ipc as sc
from netbrace.tasks.safety import scenarios
from netbrace.topology.patches import apply_unified_diff


def test_patch_round_trips():
    before = ipc.baseline_configs()["r1"]
    after = apply_unified_diff(before, sc.change_patch())
    assert after == sc._post_r1_config()


def test_change_adds_only_outbound_filter_to_r1():
    before = ipc.baseline_configs()["r1"]
    after = apply_unified_diff(before, sc.change_patch())
    # the four new policy/neighbor lines appear post, absent pre
    for line in (
        "ip prefix-list CLEANUP_OUT seq 5 permit 10.0.0.0/8 le 32",
        "ip prefix-list CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30",
        "route-map TO_R2_OUT permit 10",
        " match ip address prefix-list CLEANUP_OUT",
        "  neighbor 10.0.0.2 route-map TO_R2_OUT out",
    ):
        assert line not in before
        assert line in after
    # r2 and r3 are NOT touched by this scenario
    assert sc.CHANGE_TARGET == "r1"


def test_filtering_uses_prefix_list_not_access_list():
    """Determinism-spec hard constraint: no FRR access-list (Batfish won't model it)."""
    after = apply_unified_diff(ipc.baseline_configs()["r1"], sc.change_patch())
    assert "access-list" not in after
    assert "ip prefix-list" in after
    assert "match ip address prefix-list" in after


def test_customer_prefix_has_no_static_backup_anywhere():
    """The Class-1 invariant: the withdrawn prefix must depend on BGP alone."""
    for node, cfg in ipc.baseline_configs().items():
        assert f"ip route {ipc.CUSTOMER_PREFIX}" not in cfg, node
    # exactly one node originates it
    origins = [n for n, c in ipc.baseline_configs().items()
               if f"network {ipc.CUSTOMER_PREFIX}" in c]
    assert origins == ["r3"]


def test_registry_and_probes_well_formed():
    scn = scenarios.build("ipc")
    assert scn.name == "ipc3"
    assert ipc.CUSTOMER_PREFIX in scn.watched_prefixes
    # all loopbacks watched too (to confirm they are NOT collateral damage)
    for n in ("r1", "r2", "r3"):
        assert f"10.0.0.{n[-1]}/32" in scn.watched_prefixes
    for src, dst in scn.reachability_flows:
        assert src in ipc.NODES
        assert dst == ipc.CUSTOMER_PREFIX
    # Class-1 contract: D7 not declared (NO_ROUTE scored as D3, not double-counted)
    assert scn.forwarding_flows == []
    # D9 NOT enabled on the flagship -> its ground truth is unchanged by the
    # bgp-withdrawn addition (the has-static sibling owns the D9 discriminator).
    assert getattr(scn, "bgp_watch_prefixes", []) == []
