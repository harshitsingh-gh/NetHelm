"""Pure tests for mgmt_lockout (management-plane / OOB lockout class).

No Batfish needed: the live ground truth (D1=∅, D2=∅, D3={two jump->mgmt-IP losses},
D10={two management-reachability intent violations}, with the customer/loopback
negative controls intact) is verified by
scripts/run_extended_scenario.py --scenario mgmt_lockout. Here we lock the
structural contract for the FIXED (reframed) scenario:

  * registered + is_trap; patch round-trips; filtering uses prefix-list/route-map
    ONLY (no FRR access-list);
  * the SAME implicit-deny mechanism as `ipc`, pointed at a management intent — its
    graded value is the D10 dimension (so a reachability-only prediction misses it);
  * TWO managed devices (edge, edge2), each with its OWN mgmt prefix, neither
    permitted nor statically backed -> >= 2 reachability losses + >= 2 intent
    violations;
  * the customer prefix + all loopbacks ARE permitted and ARE watched (honest D2=∅
    negative controls), so a false-positive on them costs precision;
  * management addressing is the RFC 1918 172.16.0.0/16 block (NOT the RFC 2544
    benchmarking range the old version mislabeled).
"""

from netbrace.tasks.safety import baseline_mgmt_lockout as mgmt
from netbrace.tasks.safety import scenario_mgmt_lockout as sc
from netbrace.tasks.safety import scenarios
from netbrace.topology.patches import apply_unified_diff


def test_registered_and_is_trap():
    scn = scenarios.build("mgmt_lockout")
    assert scn.name == "mgmt_lockout"
    assert scn.is_trap is True
    assert scn.change_target == "core"
    assert set(scn.nodes) == {"jump", "core", "edge", "edge2"}


def test_patch_round_trips():
    before = mgmt.baseline_configs()["core"]
    after = apply_unified_diff(before, sc.change_patch())
    assert after == sc._post_core_config()


def test_change_adds_only_outbound_filter_to_core_toward_jump():
    before = mgmt.baseline_configs()["core"]
    after = apply_unified_diff(before, sc.change_patch())
    for line in (
        "ip prefix-list MGMT_CLEANUP_OUT seq 5 permit 10.0.0.0/8 le 32",
        "ip prefix-list MGMT_CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30",
        "ip prefix-list MGMT_CLEANUP_OUT seq 15 permit 203.0.113.0/24",
        "route-map TO_JUMP_OUT permit 10",
        " match ip address prefix-list MGMT_CLEANUP_OUT",
        "  neighbor 10.0.0.1 route-map TO_JUMP_OUT out",
    ):
        assert line not in before, line
        assert line in after, line
    # the route-map is attached toward jump (10.0.0.1) only, not toward the devices.
    assert "neighbor 10.0.0.3 route-map" not in after
    assert "neighbor 10.0.0.4 route-map" not in after


def test_only_core_changes():
    scn = scenarios.build("mgmt_lockout")
    post = scn.post_configs()
    assert post["core"] != scn.pre_configs["core"]
    for n in ("jump", "edge", "edge2"):
        assert post[n] == scn.pre_configs[n]


def test_filtering_uses_prefix_list_not_access_list():
    """Determinism-spec hard constraint: no FRR access-list (Batfish won't model it)."""
    after = apply_unified_diff(mgmt.baseline_configs()["core"], sc.change_patch())
    assert "access-list" not in after
    assert "ip prefix-list" in after
    assert "match ip address prefix-list" in after


def test_two_managed_devices_each_originate_their_own_mgmt_prefix():
    cfgs = mgmt.baseline_configs()
    assert set(mgmt.MGMT_PREFIXES) == {"edge", "edge2"}
    # RFC 1918 management block, NOT RFC 2544 benchmarking (198.18.x).
    for dev, pfx in mgmt.MGMT_PREFIXES.items():
        assert pfx.startswith("172.16.")
        assert f"network {pfx}" in cfgs[dev], dev
    assert "198.18" not in "".join(cfgs.values())  # old mislabeled range gone


def test_both_mgmt_prefixes_unpermitted_and_unbacked():
    """Class invariant: BOTH mgmt prefixes depend on BGP alone (no static backup)
    AND the cleanup filter forgets to permit either (so both are withdrawn)."""
    after = apply_unified_diff(mgmt.baseline_configs()["core"], sc.change_patch())
    for pfx in mgmt.MGMT_PREFIXES.values():
        assert f"permit {pfx}" not in after, pfx
        for node, cfg in mgmt.baseline_configs().items():
            assert f"ip route {pfx}" not in cfg, (node, pfx)


def test_customer_and_loopbacks_are_permitted_and_watched_negative_controls():
    """D2=∅ is HONEST: every watched prefix is a survivor (permitted), so a model
    false-positive on it costs precision; the mgmt prefixes are NOT hidden."""
    after = apply_unified_diff(mgmt.baseline_configs()["core"], sc.change_patch())
    scn = scenarios.build("mgmt_lockout")
    assert f"permit {mgmt.CUSTOMER_PREFIX}" in after
    assert mgmt.CUSTOMER_PREFIX in scn.watched_prefixes
    # all four loopbacks watched + covered by the 10/8 permit.
    assert "permit 10.0.0.0/8 le 32" in after
    for n in ("1", "2", "3", "4"):
        assert f"10.0.0.{n}/32" in scn.watched_prefixes
    # the mgmt prefixes are NOT in the watch set (they fire on D3/D10, not D2).
    for pfx in mgmt.MGMT_PREFIXES.values():
        assert pfx not in scn.watched_prefixes


def test_probes_have_two_mgmt_losses_and_negative_controls():
    scn = scenarios.build("mgmt_lockout")
    nodes = set(scn.nodes)
    for src, _dst in scn.reachability_flows:
        assert src in nodes
    # the two scored losses are jump -> each device mgmt-IP.
    assert scn.reachability_flows[0] == ("jump", mgmt.MGMT_IPS["edge"])
    assert scn.reachability_flows[1] == ("jump", mgmt.MGMT_IPS["edge2"])
    controls = scn.reachability_flows[2:]
    assert ("jump", mgmt.CUSTOMER_IP) in controls
    assert ("core", mgmt.MGMT_IPS["edge"]) in controls  # filter is jump-only
    # class contract: D7 not declared (NO_ROUTE scored as D3, not double-counted).
    assert scn.forwarding_flows == []


def test_declares_two_management_reachability_intents_d10():
    """The KEY fix: the management intent is GRADED via D10, not just prose. A
    reachability-only prediction now misses these and cannot score 1.0."""
    scn = scenarios.build("mgmt_lockout")
    got = {(iv.kind, iv.src, iv.dst) for iv in scn.intent_invariants}
    assert got == {
        ("reachability", "jump", mgmt.MGMT_PREFIXES["edge"]),
        ("reachability", "jump", mgmt.MGMT_PREFIXES["edge2"]),
    }


def test_structured_invariants_do_not_leak_into_model_prose():
    scn = scenarios.build("mgmt_lockout")
    prose = f"{scn.description}\n{scn.intents_text}".lower()
    for iv in scn.intent_invariants:
        assert iv.note  # exists oracle-side
        assert iv.note.lower() not in prose  # never in the model-visible prompt
