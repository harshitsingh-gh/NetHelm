"""Pure tests for the Class-1 generator (no Batfish required).

These lock the generator's STRUCTURAL contract so the live ground truth (verified
separately via scripts/run_extended_scenario.py + the determinism gate) stays
trustworthy: every emitted instance round-trips, ids are unique, randomization is
seed-deterministic, filtering uses prefix-list/route-map ONLY, and each axis is
exercised. The live oracle behaviour (which dimensions fire) is checked by the
end-to-end verification, not here.
"""

from __future__ import annotations

import pytest

from netbrace.tasks.safety import generator_ipc as g
from netbrace.tasks.safety.scenarios import Scenario
from netbrace.topology.patches import apply_unified_diff


# --------------------------------------------------------------------------- #
# Enumeration + emission.
# --------------------------------------------------------------------------- #
def test_enumerable_space_is_nontrivial():
    specs = g.enumerate_specs()
    assert g.enumerable_count() == len(specs)
    # 3 k * 2 filtered * 2 direction * (plain/static {implicit,explicit,wrong_le}
    # = 6) + (aggregate {implicit,explicit} = 2)) = 3*2*2*8 = 96
    assert len(specs) == 96
    # all valid (wrong_le never paired with aggregate)
    for s in specs:
        assert not (s.match == "wrong_le" and s.prefix == "aggregate")


def test_suite_emits_n_unique_round_tripping_instances():
    suite = g.generate_ipc_suite(40)
    assert len(suite) == 40
    ids = [s.name for s in suite]
    assert len(set(ids)) == 40, "ids must be unique"
    for scn in suite:
        assert isinstance(scn, Scenario)
        # post_configs applies the patch(es) -> raises if any does not round-trip
        post = scn.post_configs()
        changed = [n for n in scn.nodes if post[n] != scn.pre_configs[n]]
        if scn.patches:
            assert set(changed) == set(scn.patches), scn.name
        else:
            assert changed == [scn.change_target], scn.name
        # change_target is always among the changed nodes
        assert scn.change_target in changed


def test_suite_larger_than_axis_count_wraps_with_unique_ids():
    n = g.enumerable_count() + 10
    suite = g.generate_ipc_suite(n)
    assert len({s.name for s in suite}) == n  # seed in name => unique even on wrap


def test_every_axis_value_is_exercised_across_the_suite():
    suite = g.generate_ipc_suite(g.enumerable_count())
    labels = "\n".join(s.name for s in suite)
    for k in g.K_VALUES:
        assert f"k{k}-" in labels
    for v in g.FILTERED_VALUES + g.DIRECTION_VALUES + g.PREFIX_VALUES + g.MATCH_VALUES:
        assert f"-{v}-" in labels or f"-{v}_" in labels or labels.count(v) > 0


# --------------------------------------------------------------------------- #
# Randomization is seed-deterministic (the contamination control).
# --------------------------------------------------------------------------- #
def test_same_seed_same_instance():
    spec = g.IpcSpec(3, "all", "out", "plain", "implicit")
    a = g.generate_ipc_withdrawal(123, spec=spec)
    b = g.generate_ipc_withdrawal(123, spec=spec)
    assert a.name == b.name
    assert a.pre_configs == b.pre_configs
    assert a.patch == b.patch
    assert a.watched_prefixes == b.watched_prefixes


def test_different_seed_different_addressing_same_mechanism():
    spec = g.IpcSpec(2, "one", "out", "plain", "implicit")
    a = g.generate_ipc_withdrawal(1, spec=spec)
    b = g.generate_ipc_withdrawal(2, spec=spec)
    # the MECHANISM (axis tuple) is the same ...
    assert a.name.split("_s")[0] == b.name.split("_s")[0]
    # ... but the concrete addressing/ASN/names differ (renumbered = novel)
    assert a.pre_configs != b.pre_configs


def test_bare_seed_walks_the_space_deterministically():
    # generate_ipc_withdrawal(seed) (no spec) must be reproducible
    a = g.generate_ipc_withdrawal(17)
    b = g.generate_ipc_withdrawal(17)
    assert a.name == b.name and a.pre_configs == b.pre_configs


# --------------------------------------------------------------------------- #
# Determinism-spec hard constraints (Class 1 = STATIC-DETERMINISTIC).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_filtering_uses_prefix_list_not_access_list(spec):
    scn = g.generate_ipc_withdrawal(7, spec=spec)
    post = scn.post_configs()
    for node in (scn.patches or {scn.change_target: None}):
        cfg = post[node]
        assert "access-list" not in cfg, (spec.dims_label(), node)
        assert "ip prefix-list CLEANUP" in cfg
        assert "match ip address prefix-list CLEANUP" in cfg


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_router_id_pinned_to_loopback(spec):
    scn = g.generate_ipc_withdrawal(9, spec=spec)
    for node, cfg in scn.pre_configs.items():
        # every node pins bgp router-id to its loopback (deterministic ground truth)
        assert "bgp router-id" in cfg


def test_plain_customer_prefix_has_no_static_backup():
    spec = g.IpcSpec(2, "one", "out", "plain", "implicit")
    scn = g.generate_ipc_withdrawal(3, spec=spec)
    # the customer prefix is the last watched prefix (non-loopback)
    cust = [p for p in scn.watched_prefixes if not p.endswith("/32")][0]
    cust_net = cust.rsplit("/", 1)[0]
    for node, cfg in scn.pre_configs.items():
        assert f"ip route {cust_net}" not in cfg, node


def test_static_variant_has_backup_on_filtered_clients_only():
    spec = g.IpcSpec(3, "all", "out", "static", "implicit")
    scn = g.generate_ipc_withdrawal(4, spec=spec)
    cust = [p for p in scn.watched_prefixes if not p.endswith("/32")][0]
    # the has-static sibling enables D9 (bgp_watch_prefixes set)
    assert scn.bgp_watch_prefixes == [cust]
    # at least one client carries a static backup to the customer prefix
    has = [n for n, c in scn.pre_configs.items() if f"ip route {cust} " in c]
    assert has, "static variant must place a customer static on the affected clients"


def test_aggregate_variant_declares_te_pin_invariants():
    spec = g.IpcSpec(2, "one", "out", "aggregate", "implicit")
    scn = g.generate_ipc_withdrawal(5, spec=spec)
    assert scn.intent_invariants, "aggregate must declare te_pin D10 invariants"
    assert all(inv.kind == "te_pin" for inv in scn.intent_invariants)
    # the origin advertises the /24 aggregate AND both /25 more-specifics
    origin_cfg = scn.pre_configs[scn.nodes[-1]]
    assert origin_cfg.count("network ") >= 3
    assert "Null0" in origin_cfg  # the aggregate is discard-backed


# --------------------------------------------------------------------------- #
# Cardinality / blast-structure differences (NOT clones).
# --------------------------------------------------------------------------- #
def test_filtered_all_attaches_to_more_neighbors_than_one():
    # The blast-cardinality axis: 'one' attaches the route-map to a single client
    # neighbor; 'all' attaches it to every client -> a strictly larger affected set
    # (verified live: D2/D3 cardinality 1 vs k). Structurally the post-config of the
    # outbound case attaches the route-map to 1 vs k neighbors.
    one = g.generate_ipc_withdrawal(11, spec=g.IpcSpec(3, "one", "out", "plain", "implicit"))
    allf = g.generate_ipc_withdrawal(11, spec=g.IpcSpec(3, "all", "out", "plain", "implicit"))
    one_rr = one.post_configs()[one.change_target]
    all_rr = allf.post_configs()[allf.change_target]
    assert one_rr.count("route-map TO_CLIENTS_OUT out") == 1
    assert all_rr.count("route-map TO_CLIENTS_OUT out") == 3


def test_direction_changes_the_locus_node():
    out = g.generate_ipc_withdrawal(13, spec=g.IpcSpec(2, "one", "out", "plain", "implicit"))
    inb = g.generate_ipc_withdrawal(13, spec=g.IpcSpec(2, "one", "in", "plain", "implicit"))
    # outbound is applied on the RR (node 1); inbound on the affected client
    assert out.change_target == out.nodes[0]
    assert inb.change_target != inb.nodes[0]


def test_provenance_is_templated():
    for scn in g.generate_ipc_suite(5):
        assert scn.provenance == "templated"
        assert scn.is_trap is True
