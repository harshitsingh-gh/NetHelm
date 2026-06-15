"""Pure structural tests for the Family-2 (comparator wedge) + Family-3 (projection)
quiet-half generators.

Locks the SHARED generator contract via the PUBLIC API + Scenario fields only (robust to
the per-mechanism _Params/topology differences: far_as_prepend is all-eBGP like
generator_lp; med_far_as/community_*/rr_bestpath/agg_collapse are OSPF-core + eBGP;
origin_code is dual-origin with redistribute-static). The live oracle behaviour (bypass ->
pure {waypoint,intent}; no_op -> empty; 10x byte-identical) was authoritatively
re-validated on a fresh seed base (600) and saved to runs/oracle_verify_family23_20260615/.

NOTE (carried to /design-review + /red-team):
  * origin_code passed the oracle gate but its diff bundles a SET_MED route-map removal with
    the network<->redistribute-static ORIGIN swap; whether the ORIGIN step (vs a MED
    side-effect) is the true cause needs the architect's eye -- treat as provisional.
  * community_lp's no_op edits a different node than its bypass (a weak positional tell,
    like Family-1's nexthop_elim) -- worth hardening.
"""

from __future__ import annotations

import re
import pytest

from netbrace.tasks.safety import (
    generator_far_as_prepend, generator_med_far_as, generator_community_lp,
    generator_community_trigger, generator_clause_fallthrough,
    generator_remove_dead_prepend, generator_origin_code, generator_rr_bestpath,
    generator_agg_collapse,
)
from netbrace.tasks.safety.scenarios import Scenario

# (slug, module, expected combo count)
MODS = [
    ("far_as_prepend", generator_far_as_prepend, 4),
    ("med_far_as", generator_med_far_as, 4),
    ("community_lp", generator_community_lp, 4),
    ("community_trigger", generator_community_trigger, 4),
    ("clause_fallthrough", generator_clause_fallthrough, 4),
    ("remove_dead_prepend", generator_remove_dead_prepend, 4),
    ("origin_code", generator_origin_code, 4),
    ("rr_bestpath", generator_rr_bestpath, 4),
    ("agg_collapse", generator_agg_collapse, 4),
]
IDS = [m[0] for m in MODS]

_OUTCOME_LEAKS = (
    "bypass", "bypasses", "reroute", "no longer", "stops transiting", "nothing changes",
    "no change", "inert", "no-op", "no op", "still reachable", "best path", "path flips",
    "traffic shifts", " wins", " loses", "prefers ", "off the waypoint", "does not change",
    "will not change", "unaffected", "unresolvable", "elimination", "evict", " invalid",
    "less preferred", "less-preferred", "shorter", "longer", "shortest", "longest",
)


def _api(mod, slug):
    return (
        getattr(mod, f"generate_{slug}_instance"),
        getattr(mod, f"generate_{slug}_all_combos"),
        getattr(mod, f"generate_{slug}_suite"),
    )


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_enumerable_space(slug, mod, n):
    specs = mod.enumerate_specs()
    assert mod.enumerable_count() == len(specs) == n


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_all_combos_one_per_spec(slug, mod, n):
    _, all_combos, _ = _api(mod, slug)
    combos = all_combos(seed=100)
    assert len(combos) == n
    labels = {s.name.rsplit("_s", 1)[0] for s in combos}
    assert labels == {f"gen_{slug}_{s.dims_label()}" for s in mod.enumerate_specs()}


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_suite_unique_round_tripping(slug, mod, n):
    _, _, suite_fn = _api(mod, slug)
    suite = suite_fn(12)
    assert len(suite) == 12
    assert len({s.name for s in suite}) == 12, "ids must be unique"
    for scn in suite:
        assert isinstance(scn, Scenario)
        post = scn.post_configs()  # raises if the patch does not round-trip
        changed = [node for node in scn.nodes if post[node] != scn.pre_configs[node]]
        assert changed == [scn.change_target], (slug, scn.name, changed)


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_suite_wraps_unique_when_larger_than_combos(slug, mod, n):
    _, _, suite_fn = _api(mod, slug)
    suite = suite_fn(n + 5)
    assert len({s.name for s in suite}) == n + 5


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_seed_determinism_and_renumbering(slug, mod, n):
    inst, _, _ = _api(mod, slug)
    spec = mod.enumerate_specs()[0]
    a = inst(123, spec=spec)
    b = inst(123, spec=spec)
    assert a.name == b.name and a.pre_configs == b.pre_configs and a.patch == b.patch
    # different seed -> a genuinely renumbered instance (contamination control)
    c = inst(124, spec=spec)
    assert c.pre_configs != a.pre_configs, slug


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_no_bare_next_hop_self(slug, mod, n):
    """Bare 'neighbor X next-hop-self' is a Batfish no-op for eBGP-learned routes; the
    honored 'set ip next-hop' route-map form (or all-eBGP directly-connected) is used."""
    _, all_combos, _ = _api(mod, slug)
    for scn in all_combos(seed=7):
        for node, cfg in {**scn.pre_configs, **scn.post_configs()}.items():
            for line in cfg.splitlines():
                assert not re.search(r"\bneighbor\s+\S+\s+next-hop-self\b", line), (slug, node)


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_d4_and_d10_wired(slug, mod, n):
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
        assert sum(1 for p in scn.watched_prefixes if p.endswith("/32")) >= 2  # negative controls
        assert any(not p.endswith("/32") for p in scn.watched_prefixes)
        assert scn.reachability_flows and scn.reachability_flows[0][0] == wsrc


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_prompt_hygiene_no_outcome_leak(slug, mod, n):
    inst, _, _ = _api(mod, slug)
    for spec in mod.enumerate_specs():
        scn = inst(13, spec=spec)
        blob = (scn.description + " " + scn.intents_text).lower()
        for leak in _OUTCOME_LEAKS:
            assert leak not in blob, (slug, spec.dims_label(), leak)


@pytest.mark.parametrize("slug,mod,n", MODS, ids=IDS)
def test_is_trap_matches_bypass_and_provenance(slug, mod, n):
    inst, _, _ = _api(mod, slug)
    for spec in mod.enumerate_specs():
        scn = inst(5, spec=spec)
        assert scn.is_trap == ("bypass" in spec.dims_label()), (slug, scn.name)
        assert scn.provenance == "templated", slug
