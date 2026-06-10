"""Pure tests for the Class-2 route-leak generator (no Batfish required).

These lock the generator's STRUCTURAL contract so the live ground truth (verified
separately against the pinned batfish/allinone:nethelm — see the module docstring
of generator_leak for the per-combo verified dimension sets + determinism evidence)
stays trustworthy: every emitted instance round-trips, ids are unique,
randomization is seed-deterministic (the contamination control), the leak is
filtering-/policy-free (STATIC-DETERMINISTIC), the two leak KINDS produce different
structural ground-truth surfaces, and the SCOPE axis selects which /25 host flows
are affected. The live oracle behaviour (which dimensions fire) is checked by the
end-to-end verification, not here.
"""

from __future__ import annotations

import pytest

from netbrace.tasks.safety import generator_leak as g
from netbrace.tasks.safety.scenarios import Scenario


# --------------------------------------------------------------------------- #
# Enumeration + emission.
# --------------------------------------------------------------------------- #
def test_enumerable_space_is_six_combos():
    specs = g.enumerate_specs()
    assert g.enumerable_count() == len(specs)
    # 2 kinds * 3 scopes = 6 structural combos
    assert len(specs) == 6
    kinds = {s.leak_kind for s in specs}
    scopes = {s.leak_scope for s in specs}
    assert kinds == set(g.LEAK_KIND_VALUES)
    assert scopes == set(g.LEAK_SCOPE_VALUES)


def test_suite_emits_n_unique_round_tripping_instances():
    suite = g.generate_leak_suite(18)
    assert len(suite) == 18
    ids = [s.name for s in suite]
    assert len(set(ids)) == 18, "ids must be unique"
    for scn in suite:
        assert isinstance(scn, Scenario)
        # post_configs applies the patch -> raises if it does not round-trip
        post = scn.post_configs()
        changed = [n for n in scn.nodes if post[n] != scn.pre_configs[n]]
        # the leak only ever touches the leaker (the change_target)
        assert changed == [scn.change_target], scn.name
        assert scn.change_target == scn.nodes[-1]  # leaker is the third node


def test_suite_larger_than_axis_count_wraps_with_unique_ids():
    n = g.enumerable_count() + 5
    suite = g.generate_leak_suite(n)
    assert len({s.name for s in suite}) == n  # seed in name => unique even on wrap


def test_every_axis_value_is_exercised_across_the_suite():
    suite = g.generate_leak_suite(g.enumerable_count())
    labels = "\n".join(s.name for s in suite)
    for v in g.LEAK_KIND_VALUES + g.LEAK_SCOPE_VALUES:
        assert v in labels, v


# --------------------------------------------------------------------------- #
# Randomization is seed-deterministic (the contamination control).
# --------------------------------------------------------------------------- #
def test_same_seed_same_instance():
    spec = g.LeakSpec("ms_blackhole", "low_half")
    a = g.generate_leak(123, spec=spec)
    b = g.generate_leak(123, spec=spec)
    assert a.name == b.name
    assert a.pre_configs == b.pre_configs
    assert a.patch == b.patch
    assert a.watched_prefixes == b.watched_prefixes
    assert a.reachability_flows == b.reachability_flows
    assert [iv.key for iv in a.intent_invariants] == [iv.key for iv in b.intent_invariants]


def test_different_seed_renumbered_same_structure():
    spec = g.LeakSpec("ms_reroute", "both_halves")
    a = g.generate_leak(1, spec=spec)
    b = g.generate_leak(2, spec=spec)
    # the MECHANISM (axis tuple) is the same ...
    assert a.name.split("_s")[0] == b.name.split("_s")[0]
    # ... but the concrete addressing/ASN/names differ (renumbered = novel)
    assert a.pre_configs != b.pre_configs
    # same structural shape: 3 nodes, leak on the leaker, same number of flows
    assert len(a.nodes) == len(b.nodes) == 3
    assert len(a.reachability_flows) == len(b.reachability_flows)
    assert len(a.waypoint_intents) == len(b.waypoint_intents)


def test_bare_seed_walks_the_space_deterministically():
    a = g.generate_leak(17)
    b = g.generate_leak(17)
    assert a.name == b.name and a.pre_configs == b.pre_configs


def test_seed_randomizes_asn_addressing_and_names():
    spec = g.LeakSpec("ms_blackhole", "low_half")
    seen_names: set[str] = set()
    seen_asn_blocks: set[str] = set()
    for seed in range(20):
        scn = g.generate_leak(seed, spec=spec)
        # node names vary across seeds (contamination control on names)
        seen_names.update(scn.nodes)
        # the ASN appears in the prose; harvest the leaker ASN token from configs
        leaker_cfg = scn.pre_configs[scn.change_target]
        for line in leaker_cfg.splitlines():
            if line.startswith("router bgp "):
                seen_asn_blocks.add(line)
    assert len(seen_names) > 3, "node names must vary across seeds"
    assert len(seen_asn_blocks) > 1, "ASNs must vary across seeds"


def test_three_asns_are_distinct_and_private_4byte():
    for seed in range(10):
        scn = g.generate_leak(seed, spec=g.LeakSpec("ms_reroute", "low_half"))
        asns = []
        for cfg in scn.pre_configs.values():
            for line in cfg.splitlines():
                if line.startswith("router bgp "):
                    asns.append(int(line.split()[2]))
        assert len(asns) == 3
        assert len(set(asns)) == 3, "victim/transit/leaker ASNs must be distinct"
        for a in asns:
            assert g._ASN_LO <= a <= g._ASN_HI, "private 4-byte range (no 65000 collision)"


# --------------------------------------------------------------------------- #
# Determinism-spec hard constraints (Class 2 = STATIC-DETERMINISTIC).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_leak_uses_no_filter_or_policy(spec):
    scn = g.generate_leak(7, spec=spec)
    post = scn.post_configs()
    cfg = post[scn.change_target]
    # the leak is `network` + (discard static OR connected dummy) only — no policy
    assert "route-map" not in cfg, spec.dims_label()
    assert "prefix-list" not in cfg, spec.dims_label()
    assert "access-list" not in cfg, spec.dims_label()


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_router_id_pinned_to_loopback(spec):
    scn = g.generate_leak(9, spec=spec)
    for node, cfg in scn.pre_configs.items():
        assert "bgp router-id" in cfg, node


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_victim_prefix_never_withdrawn_in_configs(spec):
    """The victim's /24 is originated by the victim in BOTH snapshots (the leak
    only ADDS more-specifics) — the structural basis for the live D2 = ∅ thesis."""
    scn = g.generate_leak(11, spec=spec)
    cust = [p for p in scn.watched_prefixes if p.endswith("/24")]
    victim24 = scn.pre_configs[scn.nodes[0]]
    pre = scn.pre_configs
    post = scn.post_configs()
    vnode = scn.nodes[0]
    # the victim still originates its /24 pre and post (the leaker never touches it)
    v24 = [p for p in cust if p in pre[vnode]]
    assert v24, "victim must originate a /24 in the baseline"
    assert all(p in post[vnode] for p in v24), "victim /24 must survive the change"


# --------------------------------------------------------------------------- #
# leak_kind changes the GROUND-TRUTH structure (not a clone).
# --------------------------------------------------------------------------- #
def test_blackhole_uses_discard_static_no_reroute_dummy():
    scn = g.generate_leak(3, spec=g.LeakSpec("ms_blackhole", "low_half"))
    cfg = scn.post_configs()[scn.change_target]
    assert "blackhole" in cfg, "ms_blackhole must back the /25 with a discard static"
    # blackhole's blast is data-plane: declares forwarding + reachability probes,
    # NO waypoint intents.
    assert scn.forwarding_flows, "blackhole must declare forwarding probes"
    assert scn.reachability_flows, "blackhole must declare reachability probes"
    assert scn.waypoint_intents == [], "blackhole declares no waypoint intents"
    assert scn.intent_invariants == [], "blackhole declares no D10 invariants"


def test_reroute_uses_connected_dummy_and_declares_waypoint_intent():
    scn = g.generate_leak(3, spec=g.LeakSpec("ms_reroute", "low_half"))
    cfg = scn.post_configs()[scn.change_target]
    assert "blackhole" not in cfg, "ms_reroute must NOT discard (it delivers)"
    # ms_reroute's blast is a path/intent violation: declares waypoint intents +
    # a D10 waypoint IntentInvariant requiring transit through the victim.
    assert scn.waypoint_intents, "reroute must declare waypoint intents"
    assert scn.intent_invariants, "reroute must declare D10 waypoint invariants"
    assert all(iv.kind == "waypoint" for iv in scn.intent_invariants)
    # the required waypoint is the VICTIM (node 0)
    victim = scn.nodes[0]
    assert all(iv.waypoint == victim for iv in scn.intent_invariants)
    assert all(wp == victim for (_s, _d, wp) in scn.waypoint_intents)


def test_two_kinds_same_scope_differ_structurally():
    bh = g.generate_leak(5, spec=g.LeakSpec("ms_blackhole", "both_halves"))
    rr = g.generate_leak(5, spec=g.LeakSpec("ms_reroute", "both_halves"))
    # different declared graded surfaces (not a rename clone)
    assert bool(bh.waypoint_intents) != bool(rr.waypoint_intents)
    assert ("blackhole" in bh.post_configs()[bh.change_target]) is True
    assert ("blackhole" in rr.post_configs()[rr.change_target]) is False


# --------------------------------------------------------------------------- #
# leak_scope changes WHICH /25 host flows are affected (the element set).
# --------------------------------------------------------------------------- #
def _added_network_specifics(scn) -> list[str]:
    """The /25 `network` lines ADDED by the leak (patch '+' lines only)."""
    return [
        ln[1:].strip().split()[-1]
        for ln in scn.patch.splitlines()
        if ln.startswith("+") and "network " in ln and "/25" in ln
    ]


def test_scope_selects_which_specifics_are_leaked():
    low = g.generate_leak(8, spec=g.LeakSpec("ms_blackhole", "low_half"))
    high = g.generate_leak(8, spec=g.LeakSpec("ms_blackhole", "high_half"))
    both = g.generate_leak(8, spec=g.LeakSpec("ms_blackhole", "both_halves"))
    low_nets = _added_network_specifics(low)
    high_nets = _added_network_specifics(high)
    both_nets = _added_network_specifics(both)
    # one /25 network for the single halves, two for both
    assert len(low_nets) == 1 and low_nets[0].endswith(".0/25")
    assert len(high_nets) == 1 and high_nets[0].endswith(".128/25")
    assert len(both_nets) == 2
    # both_halves leaks strictly more specifics than either single half
    assert len(both_nets) > len(low_nets)


def test_scope_changes_the_pulled_flow_set():
    low = g.generate_leak(8, spec=g.LeakSpec("ms_reroute", "low_half"))
    both = g.generate_leak(8, spec=g.LeakSpec("ms_reroute", "both_halves"))
    # both_halves declares a waypoint intent for each leaked host -> strictly more
    assert len(both.waypoint_intents) > len(low.waypoint_intents)
    assert len(both.intent_invariants) > len(low.intent_invariants)


def test_single_half_keeps_a_negative_control_host():
    """The non-leaked half's host is probed as a negative control (it must NOT be
    pulled) — proving the blast is scoped to the leaked half."""
    low = g.generate_leak(8, spec=g.LeakSpec("ms_blackhole", "low_half"))
    # the control host (.129 for low_half) is among the transit reachability flows
    flows = {d for (s, d) in low.reachability_flows}
    # there must be at least two distinct victim-space host probes from transit
    victim_hosts = [d for d in flows if any(
        d.startswith(p.rsplit(".", 1)[0]) for p in low.watched_prefixes if p.endswith("/24")
    )]
    assert len(victim_hosts) >= 2, "single-half scope must probe a control host too"


# --------------------------------------------------------------------------- #
# Provenance / trap tagging.
# --------------------------------------------------------------------------- #
def test_provenance_is_templated_and_trap():
    for scn in g.generate_leak_suite(6):
        assert scn.provenance == "templated"
        assert scn.is_trap is True


def test_prose_states_no_outcome():
    """Prompt-hygiene: description + intents state the config edit + the intent,
    never the routing OUTCOME (no blackhole/reroute/lost/withdrawn/hijack words)."""
    banned = (
        "blackhol", "null-rout", "null rout", "reroute", "re-route", "hijack",
        "lost", "withdraw", "lpm", "longest-prefix", "pulled", "bypass",
        "drop", "loop", "unreachable",
    )
    for scn in g.generate_leak_suite(6):
        text = (scn.description + " " + scn.intents_text).lower()
        for w in banned:
            assert w not in text, (scn.name, w, text)
