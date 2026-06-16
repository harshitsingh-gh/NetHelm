"""Pure structural tests for the 3 fan-out Family-1 generators (recursive underlay
displacement): igp-summary, redistribute-ad, nexthop-elimination.

These lock the SHARED generator contract (round-trip, unique ids, seed-deterministic
randomization, D4+D10 wiring, prompt hygiene, no static-route / bare-next-hop-self
crutches) so the live ground truth stays trustworthy. The live oracle behaviour (bypass
-> pure {waypoint,intent}; no_op -> empty; 10x byte-identical) was verified end-to-end
and saved to runs/oracle_verify_family1_20260614/ (authoritative re-validation, seed
base 500, pinned batfish/allinone:nethelm @ 09817554db90). The flagship of the family,
igp-metric, has its own test_generator_igp_metric.py.
"""

from __future__ import annotations

import pytest

from netbrace.tasks.safety import generator_igp_summary as g_sum
from netbrace.tasks.safety import generator_redistribute_ad as g_red
from netbrace.tasks.safety import generator_nexthop_elim as g_nh
from netbrace.tasks.safety.scenarios import Scenario

# (slug, module, expected combo count, zero-BGP-namespace-surface in the diff?)
MODS = [
    ("igp_summary", g_sum, 4, True),
    ("redistribute_ad", g_red, 4, True),
    ("nexthop_elim", g_nh, 4, False),
]
IDS = [m[0] for m in MODS]

# OUTCOME terms that must NEVER appear in model-visible prose (config-construct terms
# like "next-hop"/"redistribute"/"prefix-list"/"cost" are legitimately present).
_OUTCOME_LEAKS = (
    "bypass", "bypasses", "reroute", "no longer", "stops transiting", "nothing changes",
    "no change", "inert", "no-op", "no op", "still reachable", "best path", "path flips",
    "traffic shifts", " wins", " loses", "prefers ", "off the waypoint", "does not change",
    "will not change", "unaffected", "unresolvable", "elimination", "evict", "invalid",
    "less preferred", "less-preferred",
)


def _api(mod, slug):
    return (
        getattr(mod, f"generate_{slug}_instance"),
        getattr(mod, f"generate_{slug}_all_combos"),
        getattr(mod, f"generate_{slug}_suite"),
    )


def _changed_diff_lines(scn) -> list[str]:
    return [l for l in scn.patch.splitlines()
            if l[:1] in "+-" and l[:3] not in ("---", "+++")]


# --------------------------------------------------------------------------- #
# Enumeration + emission.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_enumerable_space(slug, mod, n, _zbs):
    specs = mod.enumerate_specs()
    assert mod.enumerable_count() == len(specs) == n
    # every axis value set is non-empty and distinct
    for _name, vals in mod.AXES.items():
        assert len(set(vals)) == len(vals) >= 2


@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_all_combos_emits_one_per_spec(slug, mod, n, _zbs):
    _, all_combos, _ = _api(mod, slug)
    combos = all_combos(seed=100)
    assert len(combos) == n
    labels = {s.name.rsplit("_s", 1)[0] for s in combos}
    assert labels == {f"gen_{slug}_{s.dims_label()}" for s in mod.enumerate_specs()}


@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_suite_unique_round_tripping(slug, mod, n, _zbs):
    _, _, suite_fn = _api(mod, slug)
    suite = suite_fn(12)
    assert len(suite) == 12
    assert len({s.name for s in suite}) == 12, "ids must be unique"
    for scn in suite:
        assert isinstance(scn, Scenario)
        post = scn.post_configs()  # raises if the patch does not round-trip
        changed = [node for node in scn.nodes if post[node] != scn.pre_configs[node]]
        assert changed == [scn.change_target], (slug, scn.name, changed)


@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_suite_wraps_unique_when_larger_than_combos(slug, mod, n, _zbs):
    _, _, suite_fn = _api(mod, slug)
    suite = suite_fn(n + 5)
    assert len({s.name for s in suite}) == n + 5


# --------------------------------------------------------------------------- #
# Randomization is seed-deterministic (the contamination control).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_same_seed_same_instance(slug, mod, n, _zbs):
    inst, _, _ = _api(mod, slug)
    spec = mod.enumerate_specs()[0]
    a = inst(123, spec=spec)
    b = inst(123, spec=spec)
    assert a.name == b.name and a.pre_configs == b.pre_configs and a.patch == b.patch


@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_distinct_core_and_dst_asn(slug, mod, n, _zbs):
    for seed in range(8):
        p = mod._draw_params(seed)
        assert p.core_asn != p.dst_asn, (slug, p)


# --------------------------------------------------------------------------- #
# No crutches: no static routes, no bare next-hop-self (the Batfish no-op trap).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_no_static_routes_and_no_bare_next_hop_self(slug, mod, n, _zbs):
    import re
    _, all_combos, _ = _api(mod, slug)
    for scn in all_combos(seed=7):
        for node, cfg in {**scn.pre_configs, **scn.post_configs()}.items():
            assert "ip route " not in cfg, (slug, node)
            for line in cfg.splitlines():
                assert not re.search(r"\bneighbor\s+\S+\s+next-hop-self\b", line), (slug, node)
        # the honored next-hop rewrite form is the one actually used
        assert any("set ip next-hop" in c for c in scn.pre_configs.values()), slug


# --------------------------------------------------------------------------- #
# Scenario wiring (D4 + D10) + watch set + reachability.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_d4_and_d10_wired(slug, mod, n, _zbs):
    inst, _, _ = _api(mod, slug)
    for spec in mod.enumerate_specs():
        scn = inst(11, spec=spec)
        assert len(scn.waypoint_intents) == 1, slug
        wsrc, wdst, wwp = scn.waypoint_intents[0]
        assert wdst.endswith("/32")
        assert len(scn.intent_invariants) == 1, slug
        inv = scn.intent_invariants[0]
        assert inv.kind == "waypoint" and inv.src == wsrc and inv.waypoint == wwp
        assert inv.dst == wdst
        # D2 negative controls + D3 reachability probe
        assert sum(1 for p in scn.watched_prefixes if p.endswith("/32")) >= 2
        assert any(not p.endswith("/32") for p in scn.watched_prefixes)
        assert scn.reachability_flows and scn.reachability_flows[0][0] == wsrc


@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_prompt_hygiene_no_outcome_leak(slug, mod, n, _zbs):
    inst, _, _ = _api(mod, slug)
    for spec in mod.enumerate_specs():
        scn = inst(13, spec=spec)
        blob = (scn.description + " " + scn.intents_text).lower()
        for leak in _OUTCOME_LEAKS:
            assert leak not in blob, (slug, spec.dims_label(), leak)


@pytest.mark.parametrize("slug,mod,n,_zbs", MODS, ids=IDS)
def test_is_trap_matches_bypass_and_provenance_templated(slug, mod, n, _zbs):
    inst, _, _ = _api(mod, slug)
    for spec in mod.enumerate_specs():
        scn = inst(5, spec=spec)
        assert scn.is_trap == ("bypass" in spec.dims_label()), (slug, scn.name)
        assert scn.provenance == "templated", slug


# --------------------------------------------------------------------------- #
# Zero-BGP-namespace surface (the underlay-displacement claim): for the
# IGP/redistribution mechanisms the diff must touch NO BGP best-path attribute.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slug,mod,n,zbs", MODS, ids=IDS)
def test_zero_bgp_surface_when_claimed(slug, mod, n, zbs):
    if not zbs:
        pytest.skip(f"{slug} edits BGP policy by design (next-hop-self removal)")
    inst, _, _ = _api(mod, slug)
    forbidden = ("local-preference", "as-path", "set metric", "next-hop", "remote-as")
    for spec in mod.enumerate_specs():
        scn = inst(3, spec=spec)
        changed = _changed_diff_lines(scn)
        assert changed, (slug, spec.dims_label())
        for line in changed:
            low = line.lower()
            for tok in forbidden:
                assert tok not in low, (slug, spec.dims_label(), tok, line)
