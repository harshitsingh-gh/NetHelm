"""Pure tests for the Family-1 igp-metric generator (recursive underlay displacement).

These lock the generator's STRUCTURAL contract so the live ground truth stays
trustworthy: every emitted instance round-trips, ids are unique, randomization is
seed-deterministic (the contamination control), the diff touches ONLY an `ip ospf
cost` line (ZERO BGP-namespace surface — the whole point vs lp_waypoint), the two
knobs edit DIFFERENT interfaces, the no_op effect is inert, and BOTH D4 (waypoint)
and D10 (intent) are wired. The live oracle behaviour is checked end-to-end, not here.

Live-verified (2026-06-14, pinned batfish/allinone:nethelm @ 09817554db90, seed base
100; artifact runs/oracle_verify_igp_metric_20260614/signature_and_determinism.json):
  * raise_way/bypass -> D4 waypoint + D10 intent ONLY (D1/D2/D3/D5/D7=∅); reachability
    survives via alt
  * lower_alt/bypass -> D4 + D10 ONLY
  * *_no_op          -> COMPLETELY EMPTY across all dims
  * both bypass combos 10x byte-identical (determinism gate)
"""

from __future__ import annotations

import pytest

from netbrace.tasks.safety import generator_igp_metric as g
from netbrace.tasks.safety.scenarios import Scenario


# --------------------------------------------------------------------------- #
# Enumeration + emission.
# --------------------------------------------------------------------------- #
def test_enumerable_space_is_four_combos():
    specs = g.enumerate_specs()
    assert g.enumerable_count() == len(specs) == 4
    assert {s.knob for s in specs} == set(g.KNOB_VALUES)
    assert {s.effect for s in specs} == set(g.EFFECT_VALUES)


def test_all_combos_emits_one_per_spec():
    combos = g.generate_igp_metric_all_combos(seed=100)
    assert len(combos) == 4
    labels = {s.name.rsplit("_s", 1)[0] for s in combos}
    assert labels == {f"gen_igp_metric_{s.dims_label()}" for s in g.enumerate_specs()}


def test_all_combos_without_noop_drops_the_empty_gt_variants():
    combos = g.generate_igp_metric_all_combos(seed=100, include_noop=False)
    assert len(combos) == 2
    assert all("no_op" not in s.name for s in combos)
    assert all(s.is_trap for s in combos)


def test_suite_emits_n_unique_round_tripping_instances():
    suite = g.generate_igp_metric_suite(20)
    assert len(suite) == 20
    assert len({s.name for s in suite}) == 20, "ids must be unique"
    for scn in suite:
        assert isinstance(scn, Scenario)
        post = scn.post_configs()  # raises if the patch does not round-trip
        changed = [n for n in scn.nodes if post[n] != scn.pre_configs[n]]
        assert changed == [scn.change_target], scn.name
        assert scn.change_target == scn.nodes[0]  # the change is always on src


def test_suite_larger_than_combo_count_wraps_with_unique_ids():
    n = g.enumerable_count() + 5
    suite = g.generate_igp_metric_suite(n)
    assert len({s.name for s in suite}) == n


# --------------------------------------------------------------------------- #
# Randomization is seed-deterministic (the contamination control).
# --------------------------------------------------------------------------- #
def test_same_seed_same_instance():
    spec = g.IgpMetricSpec("raise_way", "bypass")
    a = g.generate_igp_metric_instance(123, spec=spec)
    b = g.generate_igp_metric_instance(123, spec=spec)
    assert a.name == b.name and a.pre_configs == b.pre_configs and a.patch == b.patch
    assert a.waypoint_intents == b.waypoint_intents


def test_different_seed_different_addressing_same_mechanism():
    spec = g.IgpMetricSpec("lower_alt", "bypass")
    a = g.generate_igp_metric_instance(1, spec=spec)
    b = g.generate_igp_metric_instance(2, spec=spec)
    assert a.name.split("_s")[0] == b.name.split("_s")[0]  # same mechanism
    assert a.pre_configs != b.pre_configs                  # renumbered


def test_seeds_draw_distinct_core_and_dst_asn():
    # core (src/way/alt iBGP) and dst (eBGP customer AS) must be different ASes
    for seed in range(10):
        p = g._draw_params(seed)
        assert p.core_asn != p.dst_asn, p


# --------------------------------------------------------------------------- #
# The mechanism: ZERO BGP-namespace surface — the diff is one `ip ospf cost` line.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_diff_touches_only_ospf_cost(spec):
    """The whole point vs lp_waypoint: the decisive change lives in the IGP. The
    changed (+/-) lines of the diff must be `ip ospf cost` lines and nothing else —
    no BGP/route-map/network token moves."""
    scn = g.generate_igp_metric_instance(7, spec=spec)
    changed = [l for l in scn.patch.splitlines()
               if l[:1] in "+-" and l[:3] not in ("---", "+++")]
    assert changed, spec.dims_label()
    for line in changed:
        assert "ip ospf cost" in line, (spec.dims_label(), line)


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_no_static_routes_anywhere(spec):
    """Recursive resolution must ride OSPF, never a static crutch (the crutch-killer
    invariant the OSPF-underlay family exists to enforce)."""
    scn = g.generate_igp_metric_instance(7, spec=spec)
    for node, cfg in scn.post_configs().items():
        assert "ip route " not in cfg, (spec.dims_label(), node)


def test_egress_uses_routemap_nexthop_not_bare_next_hop_self():
    """Batfish treats bare `next-hop-self` as a no-op for eBGP-learned routes, so the
    egress next-hop MUST be rewritten via the honored `set ip next-hop <lo>` form."""
    scn = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec("raise_way", "bypass"))
    way = scn.nodes[1]
    cfg = scn.pre_configs[way]
    assert "set ip next-hop" in cfg
    assert "next-hop-self" not in cfg, "must not rely on bare next-hop-self"


def _ospf_costs_per_iface(src_cfg: str) -> dict[str, int]:
    """Parse src's PRE config into {iface: ospf_cost}. eth1=way side, eth2=alt side."""
    out: dict[str, int] = {}
    cur: str | None = None
    for raw in src_cfg.splitlines():
        line = raw.strip()
        if line.startswith("interface "):
            cur = line.split()[1]
        elif line.startswith("ip ospf cost ") and cur is not None:
            out[cur] = int(line.split()[-1])
    return out


def test_ibgp_over_loopbacks_and_strict_cost_gap():
    # The costs are drawn per-seed (contamination control), so we parse them and assert
    # the STRICT gap invariant, never a literal value (no hardcoded fingerprint).
    scn = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec("raise_way", "bypass"))
    src_cfg = scn.pre_configs[scn.nodes[0]]
    assert "update-source lo" in src_cfg                # iBGP over loopbacks
    costs = _ospf_costs_per_iface(src_cfg)
    # exactly the two underlay interfaces carry an ospf cost (eth1=way, eth2=alt)
    assert set(costs) == {"eth1", "eth2"}, costs
    # baseline: way side (eth1) STRICTLY cheaper than alt side (eth2) so way wins PRE
    assert costs["eth1"] < costs["eth2"], costs


def _patch_cost_edit(patch: str) -> tuple[int, int]:
    """Parse a single-line `ip ospf cost` swap patch -> (removed_pre, added_post)."""
    removed = added = None
    for line in patch.splitlines():
        if line[:3] in ("---", "+++") or "ip ospf cost" not in line:
            continue
        if line.startswith("-"):
            removed = int(line.split()[-1])
        elif line.startswith("+"):
            added = int(line.split()[-1])
    assert removed is not None and added is not None, patch
    return removed, added


def test_two_knobs_edit_two_distinct_interfaces():
    # Costs are per-seed; assert INVARIANTS (raise/lower direction + crossing the PRE
    # gap + distinct edited interfaces), never literal values.
    rw_scn = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec("raise_way", "bypass"))
    la_scn = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec("lower_alt", "bypass"))
    # The PRE alt/way costs from the (shared seed) src config.
    pre = _ospf_costs_per_iface(rw_scn.pre_configs[rw_scn.nodes[0]])
    way_pre, alt_pre = pre["eth1"], pre["eth2"]

    rw_removed, rw_added = _patch_cost_edit(rw_scn.patch)
    la_removed, la_added = _patch_cost_edit(la_scn.patch)

    # raise_way is a RAISE that crosses ABOVE the PRE alt cost (so alt now wins).
    assert rw_added > rw_removed, ("raise_way must raise", rw_removed, rw_added)
    assert rw_removed == way_pre and rw_added > alt_pre, (rw_removed, rw_added, way_pre, alt_pre)
    # lower_alt is a LOWER that drops BELOW the PRE way cost (so alt now wins).
    assert la_added < la_removed, ("lower_alt must lower", la_removed, la_added)
    assert la_removed == alt_pre and la_added < way_pre, (la_removed, la_added, alt_pre, way_pre)
    # The two edits touch DIFFERENT interfaces: their removed (pre) costs differ.
    assert rw_removed != la_removed, (rw_removed, la_removed)


# --------------------------------------------------------------------------- #
# The effect axis: bypass is a trap (D4+D10); no_op is an inert empty-GT change.
# --------------------------------------------------------------------------- #
def test_bypass_is_trap_no_op_is_not():
    for knob in g.KNOB_VALUES:
        byp = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec(knob, "bypass"))
        noo = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec(knob, "no_op"))
        assert byp.is_trap is True and noo.is_trap is False, knob


def test_noop_change_is_a_real_one_line_edit_not_empty():
    for knob in g.KNOB_VALUES:
        scn = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec(knob, "no_op"))
        assert scn.patch.strip(), knob
        post = scn.post_configs()
        assert post[scn.change_target] != scn.pre_configs[scn.change_target], knob


# --------------------------------------------------------------------------- #
# Scenario wiring (D4 + D10) + prompt hygiene.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_waypoint_and_intent_wired(spec):
    scn = g.generate_igp_metric_instance(11, spec=spec)
    src, way = scn.nodes[0], scn.nodes[1]
    # D4
    assert len(scn.waypoint_intents) == 1
    wsrc, wdst, wwp = scn.waypoint_intents[0]
    assert wsrc == src and wwp == way and wdst.endswith("/32")
    # D10: a matching kind="waypoint" invariant so the intent dimension fires too
    assert len(scn.intent_invariants) == 1
    inv = scn.intent_invariants[0]
    assert inv.kind == "waypoint" and inv.src == src and inv.waypoint == way
    assert inv.dst == wdst
    # D2 watch set: 3 core loopbacks + the customer /24
    assert sum(1 for p in scn.watched_prefixes if p.endswith("/32")) == 3
    assert any(not p.endswith("/32") for p in scn.watched_prefixes)
    # D3 reachability probe present
    assert scn.reachability_flows and scn.reachability_flows[0][0] == src


@pytest.mark.parametrize("spec", g.enumerate_specs())
def test_prompt_hygiene_no_outcome_leak(spec):
    """Prose = config edit + intent ONLY. Never the routing outcome (the bypass and
    no_op variants must read identically in style)."""
    scn = g.generate_igp_metric_instance(13, spec=spec)
    blob = (scn.description + " " + scn.intents_text).lower()
    for leak in (
        "becomes preferred", "becomes the best", "bypass", "bypasses", "no longer",
        "stops transiting", "nothing changes", "no change", "inert", "no-op", "no op",
        "still reachable", "best path flips", "path flips", "traffic shifts",
        "wins", "loses", "prefers alt", "prefers way", "off the waypoint", "reroute",
        "does not change", "will not change", "unaffected", "recursion", "next-hop",
    ):
        assert leak not in blob, (spec.dims_label(), leak)


def test_bypass_and_noop_descriptions_are_same_shape():
    for knob in g.KNOB_VALUES:
        b = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec(knob, "bypass")).description
        n = g.generate_igp_metric_instance(0, spec=g.IgpMetricSpec(knob, "no_op")).description
        # identical sentence skeleton up to the named interface / value
        assert b.split("`eth")[0] == n.split("`eth")[0]


def test_provenance_is_templated():
    for scn in g.generate_igp_metric_suite(4):
        assert scn.provenance == "templated"
