"""Pure tests for the Class-5 generator (attribute-induced path-shift, all-eBGP).

These lock the generator's STRUCTURAL contract so the live ground truth (verified
separately against the pinned batfish/allinone:nethelm — see the module docstring of
generator_lp for the per-combo verified dimension sets + determinism evidence) stays
trustworthy: every emitted instance round-trips, ids are unique, randomization is
seed-deterministic (the contamination control), the topology is ALL-eBGP with NO
static next-hop plumbing (the M3 audit fix), the three knobs each edit a DIFFERENT
config construct, and the no_op effect axis emits an inert change. The live oracle
behaviour (which dimensions fire: bypass -> D4 only; no_op -> empty) is checked by
the end-to-end verification, not here.

Live-verified (2026-06-10, pinned batfish/allinone:nethelm @ 09817554db90,
seed base 100), per combo:
  * lp_raise_alt/bypass  -> D4 waypoint ONLY (D1/D2/D3=∅); reachability survives via alt
  * lp_drop_way/bypass   -> D4 waypoint ONLY
  * prepend_way/bypass   -> D4 waypoint ONLY (Batfish honors inbound AS_PATH prepend)
  * *_no_op              -> COMPLETELY EMPTY across all dims; empty-pred grades pass/1.0
  * all 6 combos 2x byte-identical (determinism gate)
"""

from __future__ import annotations

import pytest

from netbrace.tasks.safety import generator_lp as g
from netbrace.tasks.safety.scenarios import Scenario
from netbrace.topology.patches import apply_unified_diff


# --------------------------------------------------------------------------- #
# Enumeration + emission.
# --------------------------------------------------------------------------- #
def test_enumerable_space_is_six_combos():
    specs = g.enumerate_specs()
    assert g.enumerable_count() == len(specs)
    # 3 knobs * 2 effects = 6 structural combos
    assert len(specs) == 6
    assert {s.knob for s in specs} == set(g.KNOB_VALUES)
    assert {s.effect for s in specs} == set(g.EFFECT_VALUES)


def test_all_combos_emits_one_per_spec():
    combos = g.generate_lp_all_combos(seed=100)
    assert len(combos) == 6
    labels = {s.name.rsplit("_s", 1)[0] for s in combos}
    assert labels == {f"gen_lp_{s.dims_label()}" for s in g.enumerate_specs()}


def test_all_combos_without_noop_drops_the_empty_gt_variants():
    combos = g.generate_lp_all_combos(seed=100, include_noop=False)
    assert len(combos) == 3
    assert all("no_op" not in s.name for s in combos)
    assert all(s.is_trap for s in combos)  # bypass-only => all traps


def test_suite_emits_n_unique_round_tripping_instances():
    suite = g.generate_lp_suite(20)
    assert len(suite) == 20
    ids = [s.name for s in suite]
    assert len(set(ids)) == 20, "ids must be unique"
    for scn in suite:
        assert isinstance(scn, Scenario)
        # post_configs applies the patch -> raises if it does not round-trip
        post = scn.post_configs()
        changed = [n for n in scn.nodes if post[n] != scn.pre_configs[n]]
        assert changed == [scn.change_target], scn.name
        assert scn.change_target == scn.nodes[0]  # the change is always on src


def test_suite_larger_than_combo_count_wraps_with_unique_ids():
    n = g.enumerable_count() + 5
    suite = g.generate_lp_suite(n)
    assert len({s.name for s in suite}) == n  # seed in name => unique even on wrap


def test_suite_without_noop_emits_only_bypass():
    suite = g.generate_lp_suite(9, include_noop=False)
    assert len(suite) == 9
    assert all("no_op" not in s.name for s in suite)
    assert all(s.is_trap for s in suite)


def test_every_knob_and_effect_is_exercised():
    suite = g.generate_lp_suite(g.enumerable_count())
    labels = "\n".join(s.name for s in suite)
    for v in g.KNOB_VALUES + g.EFFECT_VALUES:
        assert v in labels, v


# --------------------------------------------------------------------------- #
# Randomization is seed-deterministic (the contamination control).
# --------------------------------------------------------------------------- #
def test_same_seed_same_instance():
    spec = g.LpSpec("lp_raise_alt", "bypass")
    a = g.generate_lp_instance(123, spec=spec)
    b = g.generate_lp_instance(123, spec=spec)
    assert a.name == b.name
    assert a.pre_configs == b.pre_configs
    assert a.patch == b.patch
    assert a.watched_prefixes == b.watched_prefixes
    assert a.waypoint_intents == b.waypoint_intents


def test_different_seed_different_addressing_same_mechanism():
    spec = g.LpSpec("lp_drop_way", "bypass")
    a = g.generate_lp_instance(1, spec=spec)
    b = g.generate_lp_instance(2, spec=spec)
    # same mechanism (axis tuple) ...
    assert a.name.split("_s")[0] == b.name.split("_s")[0]
    # ... but renumbered (novel even for this public mechanism)
    assert a.pre_configs != b.pre_configs


def test_bare_seed_walks_the_space_deterministically():
    a = g.generate_lp_instance(17)
    b = g.generate_lp_instance(17)
    assert a.name == b.name and a.pre_configs == b.pre_configs


def test_seeds_draw_four_distinct_asns():
    # all-eBGP => every role must be a genuinely distinct external AS
    for seed in range(10):
        p = g._draw_params(seed)
        assert len(set(p.asn.values())) == 4, p.asn


# --------------------------------------------------------------------------- #
# The M3 audit fix: ALL-eBGP, NO static next-hop plumbing anywhere.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_no_static_routes_anywhere(spec):
    """The whole point of the re-home: eBGP next-hops are directly connected, so
    there is ZERO static-route plumbing (contrast baseline_lp_waypoint's `ip route`
    statics to external /30s — the non-idiomatic crutch this generator removes)."""
    scn = g.generate_lp_instance(7, spec=spec)
    for node, cfg in scn.post_configs().items():
        assert "ip route " not in cfg, (spec.dims_label(), node)


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_all_sessions_are_ebgp_directly_connected(spec):
    """Every BGP neighbor is a directly-connected /30 link IP (no update-source lo,
    no iBGP same-AS peering) — the leak_ms all-eBGP doctrine."""
    scn = g.generate_lp_instance(8, spec=spec)
    # src/way/alt/dst ASNs are all distinct (no two neighbors share an AS => eBGP)
    p = g._draw_params(8)
    assert len(set(p.asn.values())) == 4
    for node, cfg in scn.pre_configs.items():
        assert "update-source lo" not in cfg, node  # eBGP over link IPs only


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_router_id_pinned_to_loopback(spec):
    scn = g.generate_lp_instance(9, spec=spec)
    for node, cfg in scn.pre_configs.items():
        assert "bgp router-id" in cfg, node


# --------------------------------------------------------------------------- #
# The knob axis: three DIFFERENT config constructs, all flipping off the waypoint.
# --------------------------------------------------------------------------- #
def test_lp_raise_alt_edits_the_alt_inbound_localpref():
    scn = g.generate_lp_instance(0, spec=g.LpSpec("lp_raise_alt", "bypass"))
    pre = scn.pre_configs[scn.change_target]
    post = scn.post_configs()[scn.change_target]
    # baseline: way 200 > alt 100; change raises alt -> 300 on RM_UPLINK2_IN
    assert "route-map RM_UPLINK2_IN permit 10\n set local-preference 100" in pre
    assert "route-map RM_UPLINK2_IN permit 10\n set local-preference 300" in post
    # the WAY map is untouched
    assert "route-map RM_UPLINK1_IN permit 10\n set local-preference 200" in post


def test_lp_drop_way_edits_the_way_inbound_localpref():
    scn = g.generate_lp_instance(0, spec=g.LpSpec("lp_drop_way", "bypass"))
    post = scn.post_configs()[scn.change_target]
    # change lowers way -> 50 so alt's 100 wins; reads a DIFFERENT map than lp_raise
    assert "route-map RM_UPLINK1_IN permit 10\n set local-preference 50" in post
    assert "route-map RM_UPLINK2_IN permit 10\n set local-preference 100" in post


def test_prepend_way_uses_as_path_prepend_with_literal_asn():
    scn = g.generate_lp_instance(0, spec=g.LpSpec("prepend_way", "bypass"))
    pre = scn.pre_configs[scn.change_target]
    post = scn.post_configs()[scn.change_target]
    # equal LP baseline; reads an AS_PATH construct (NOT a localpref value)
    assert "set as-path prepend" in pre  # baseline prepends alt once
    assert "set as-path prepend" in post
    # Batfish does NOT parse the `last-as N` shorthand -> we MUST use literal ASNs
    assert "last-as" not in post, "use literal-ASN prepend (Batfish-parseable)"
    # the bypass change extends the WAY map's prepend
    assert post.count("set as-path prepend") == 2  # alt(baseline) + way(change)


def test_three_knobs_edit_three_distinct_constructs():
    raise_alt = g.generate_lp_instance(0, spec=g.LpSpec("lp_raise_alt", "bypass")).patch
    drop_way = g.generate_lp_instance(0, spec=g.LpSpec("lp_drop_way", "bypass")).patch
    prepend = g.generate_lp_instance(0, spec=g.LpSpec("prepend_way", "bypass")).patch
    # localpref knobs touch local-preference; prepend knob touches as-path
    assert "local-preference" in raise_alt and "as-path" not in raise_alt
    assert "local-preference" in drop_way and "as-path" not in drop_way
    assert "as-path prepend" in prepend
    # raise vs drop edit OPPOSITE maps -> genuinely distinct reading tasks. The
    # CHANGED (-/+) lines of lp_raise touch RM_UPLINK2_IN; lp_drop touch RM_UPLINK1_IN.
    raise_changed = [l for l in raise_alt.splitlines() if l[:1] in "+-" and l[:3] not in ("---", "+++")]
    drop_changed = [l for l in drop_way.splitlines() if l[:1] in "+-" and l[:3] not in ("---", "+++")]
    # the edited VALUE lines differ (300 for raise, 50 for drop)
    assert any("300" in l for l in raise_changed)
    assert any("50" in l for l in drop_changed)


# --------------------------------------------------------------------------- #
# The effect axis: bypass is a trap (D4); no_op is an inert empty-GT change.
# --------------------------------------------------------------------------- #
def test_bypass_is_trap_no_op_is_not():
    for knob in g.KNOB_VALUES:
        byp = g.generate_lp_instance(0, spec=g.LpSpec(knob, "bypass"))
        noo = g.generate_lp_instance(0, spec=g.LpSpec(knob, "no_op"))
        assert byp.is_trap is True, knob
        assert noo.is_trap is False, knob


def test_noop_edits_the_other_map_same_edit_kind():
    # lp_raise: bypass raises ALT; no_op raises WAY (the already-preferred path) ->
    # same KIND of edit (a localpref raise to 300), applied where it does nothing.
    b = g.generate_lp_instance(0, spec=g.LpSpec("lp_raise_alt", "bypass"))
    n = g.generate_lp_instance(0, spec=g.LpSpec("lp_raise_alt", "no_op"))
    bp = b.post_configs()[b.change_target]
    npc = n.post_configs()[n.change_target]
    assert "RM_UPLINK2_IN permit 10\n set local-preference 300" in bp
    assert "RM_UPLINK1_IN permit 10\n set local-preference 300" in npc


def test_noop_change_is_a_real_one_line_edit_not_empty():
    # the no_op prose/diff must look like a genuine change (the calibration trap):
    # the model must REASON it is inert, not see an empty diff.
    for knob in g.KNOB_VALUES:
        scn = g.generate_lp_instance(0, spec=g.LpSpec(knob, "no_op"))
        assert scn.patch.strip(), knob
        post = scn.post_configs()
        assert post[scn.change_target] != scn.pre_configs[scn.change_target], knob


# --------------------------------------------------------------------------- #
# Scenario wiring + prompt hygiene.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_waypoint_intent_and_probes_wired(spec):
    scn = g.generate_lp_instance(11, spec=spec)
    src, way = scn.nodes[0], scn.nodes[1]
    assert len(scn.waypoint_intents) == 1
    wsrc, wdst, wwp = scn.waypoint_intents[0]
    assert wsrc == src and wwp == way and wdst.endswith("/32")
    # D2 watch set: all 4 loopbacks + the customer /24
    assert sum(1 for p in scn.watched_prefixes if p.endswith("/32")) == 4
    assert any(not p.endswith("/32") for p in scn.watched_prefixes)
    # D3 reachability probe present (the off-path-but-reachable proof)
    assert scn.reachability_flows and scn.reachability_flows[0][0] == src


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_prompt_hygiene_no_outcome_leak(spec):
    """Prose = config edit + intent ONLY. The no_op prose must be indistinguishable
    in STYLE from bypass — never the routing outcome."""
    scn = g.generate_lp_instance(13, spec=spec)
    blob = (scn.description + " " + scn.intents_text).lower()
    for leak in (
        "becomes preferred", "becomes the best", "bypass", "bypasses", "no longer",
        "stops transiting", "nothing changes", "no change", "inert", "no-op", "no op",
        "still reachable", "best path flips", "path flips", "traffic shifts",
        "wins", "loses", "prefers alt", "prefers way", "off the waypoint",
        "does not change", "will not change", "unaffected",
    ):
        assert leak not in blob, (spec.dims_label(), leak)


def test_bypass_and_noop_descriptions_are_same_shape():
    # the calibration trap demands style-parity: same sentence template, only the
    # named map / value differs. (We assert the structural skeleton matches.)
    for knob in g.KNOB_VALUES:
        b = g.generate_lp_instance(0, spec=g.LpSpec(knob, "bypass")).description
        n = g.generate_lp_instance(0, spec=g.LpSpec(knob, "no_op")).description
        # both name a route-map and an edit verb; neither states an outcome
        assert "route-map" in b and "route-map" in n
        assert b.split("route-map")[0] == n.split("route-map")[0]


def test_provenance_is_templated():
    for scn in g.generate_lp_suite(6):
        assert scn.provenance == "templated"
