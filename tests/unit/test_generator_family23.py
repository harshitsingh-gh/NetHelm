"""Pure structural tests for the Family-2 (comparator wedge) + Family-3 (projection)
quiet-half generators.

Locks the SHARED generator contract via the PUBLIC API + Scenario fields only (robust to
the per-mechanism _Params/topology differences: far_as_prepend is all-eBGP like
generator_lp; med_far_as/community_*/rr_bestpath/agg_collapse are OSPF-core + eBGP;
origin_code is dual-origin with redistribute-static). The live oracle behaviour (bypass ->
pure {waypoint,intent}; no_op -> empty; 10x byte-identical) was authoritatively
re-validated on a fresh seed base (600) and saved to runs/oracle_verify_family23_20260615/.

NOTE (carried to /design-review + /red-team):
  * origin_code (RESOLVED by network-architect 2026-06-15, audit M2/M3/M4):
      - The bypass diff does NOT remove the MED. The `set metric <m>` is RELOCATED from the
        outbound SET_MED_<role> route-map into the redistribution route-map REDIST_CUST; the
        advertised MED (200 way / 50 alt) is PRESERVED across the swap (rendered + confirmed,
        seeds 600/601). So the bypass changes exactly ONE routing-relevant attribute: ORIGIN.
      - Cause attribution is two-step and now stated honestly in the generator docstring:
        PRE the ORIGIN step (RFC 4271 §9.1.2.2 (b), igp<incomplete) is decisive; POST/bypass
        the ORIGIN step TIES and the decision falls through to the MED step §9.1.2.2 (c)
        (50<200) -- the MED is the real POST discriminator, ungated by the ORIGIN flip. NOT
        "ORIGIN is decisive POST". No longer provisional.
      - Gameability tell CLOSED: the no_op now edits the CUSTOMER prefix (re-originate via
        redistribute static + `set origin <pre-origin>`, best-path-neutral) instead of the
        OWN loopback, so BOTH twins name the customer prefix in their +/- diff lines. A
        purely syntactic "does the patch touch the customer prefix?" heuristic can no longer
        separate trap from calibration; only reading the `set origin` neutralizer does. The
        no_op GT stays COMPLETELY EMPTY and 10x byte-identical (live-verified on the pinned
        digest, runs/oracle_verify_origin_code_fix_20260615/).
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


# --------------------------------------------------------------------------- #
# origin_code-SPECIFIC assertions (audit M2/M3/M4 fixes). These lock the gameability
# closure + the MED-relocation/RFC-citation honesty for the origin_code family only.
# --------------------------------------------------------------------------- #
def _diff_pm_lines(scn):
    """The +/- (non-header) lines of the change_target's PRE->POST diff."""
    pre = scn.pre_configs[scn.change_target].splitlines()
    post = scn.post_configs()[scn.change_target].splitlines()
    import difflib
    return [l for l in difflib.unified_diff(pre, post, lineterm="")
            if (l.startswith("+") or l.startswith("-"))
            and not l.startswith(("+++", "---"))]


def test_origin_code_both_twins_name_customer_prefix():
    """audit-M3 gameability fix: a purely syntactic 'does the patch touch the customer
    prefix?' heuristic must NOT separate trap (bypass) from calibration (no_op). BOTH must
    add/remove a +/- diff line that literally names the customer /24, and NEITHER may hide
    on the OWN loopback /32 (the OLD no_op tell)."""
    mod = generator_origin_code
    for spec in mod.enumerate_specs():
        scn = mod.generate_origin_code_instance(600, spec=spec)
        cust = scn.watched_prefixes[-1]              # the customer /24 (last watched)
        assert not cust.endswith("/32"), cust         # sanity: it's the /24, not a loopback
        pm = _diff_pm_lines(scn)
        cust_lines = [l for l in pm if cust in l]
        assert cust_lines, (spec.dims_label(), "no +/- diff line names the customer prefix")
        # the no_op must NOT revert to the old loopback-redistribute tell
        assert not any(("REDIST_LOOP" in l or "LOOP_PL" in l
                        or "redistribute connected" in l) for l in pm), spec.dims_label()


def test_origin_code_twins_are_diff_shape_identical_set_origin_clause_decides():
    """origin_code twins: CHANGED-LINE symmetry (HELD OUT of the headline for hunk geometry).
    The bypass and no_op twins of a given KNOB produce byte-identical CHANGED +/- LINES (a
    CUST_PL seq renumber + the SAME flipped `set origin` token), so no single-feature AND no
    2-feature XOR of the CHANGED LINES separates trap from calibration. HOWEVER the full
    unified-diff hunk GEOMETRY differs (bypass 1 hunk, no_op 2 hunks — the no_op edits the decoy
    clause farther from the renumber), which is why origin_code is HELD OUT of the scored
    headline (run_sweep.REROUTE_DIFFSHAPE_LEAKY; test_reroute_probe_leak.py). The ONLY routing
    difference is WHICH
    route-map clause the rewritten origin governs:
      * bypass edits CLAUSE 10 (the customer /24 clause, matched by CUST_PL) -> the customer
        copy's ORIGIN flips -> ORIGIN tie collapses -> latent MED decides -> reroute;
      * no_op  edits CLAUSE 20 (the INERT decoy clause, matched by DECOY_PL whose /24 has no
        static) -> no routing effect -> empty GT.
    Telling them apart requires TRACING the route-map (which clause governs the customer copy
    on the inspection path) -- genuine best-path reasoning, not a keyword/value/shape grep."""
    mod = generator_origin_code
    for knob in ("way_to_incomplete", "alt_to_igp"):
        bypass = mod.generate_origin_code_instance(
            600, spec=mod.OriginCodeSpec(knob, "bypass"))
        no_op = mod.generate_origin_code_instance(
            600, spec=mod.OriginCodeSpec(knob, "no_op"))
        pm_b = _diff_pm_lines(bypass)
        pm_n = _diff_pm_lines(no_op)
        # (a) BOTH carry a `set origin` +/- line and a CUST_PL renumber that names the /24.
        for pm, eff in ((pm_b, "bypass"), (pm_n, "no_op")):
            assert any("set origin" in l for l in pm), (knob, eff, "no set origin in diff")
            assert any("CUST_PL" in l and "/24" in l for l in pm), (knob, eff, "no CUST_PL /24")
        # (b) the CHANGED +/- LINES are byte-identical between the twins (line-level symmetry).
        assert pm_b == pm_n, (knob, "bypass and no_op CHANGED LINES are NOT identical", pm_b, pm_n)
        # (b') BUT the full unified-diff hunk GEOMETRY is asymmetric — the reason origin_code is
        #      HELD OUT of the headline (bypass = 1 hunk, no_op = 2 hunks).
        assert bypass.patch.count("@@ -") != no_op.patch.count("@@ -"), (
            knob, "expected asymmetric hunk geometry (the held-out reason)")
        # (c) the flipped `set origin` token is the SAME for both effects (== flip of PRE);
        #     the token therefore carries NO label info -- only the clause does.
        pre = "igp" if knob == "way_to_incomplete" else "incomplete"
        flip = "incomplete" if pre == "igp" else "igp"
        added_b = [l[1:] for l in pm_b if l.startswith("+")]
        assert any(f"set origin {flip}" in l for l in added_b), (knob, flip)
        assert not any(f"set origin {pre}" in l for l in
                       [l[1:] for l in pm_b if l.startswith("+")]), (knob, "pre token re-added")
        # (d) the DISCRIMINATOR is in the POST config, not the diff: the bypass changes the
        #     CUSTOMER clause's origin (clause 10) while the no_op leaves it at PRE.
        def _cust_clause_origin(scn):
            post = scn.post_configs()[scn.change_target].splitlines()
            # clause 10 is the first route-map clause; its `set origin` governs the customer /24.
            for i, l in enumerate(post):
                if l.strip() == "route-map REDIST_CUST permit 10":
                    for l2 in post[i:i + 5]:
                        m = re.search(r"set origin (\w+)", l2)
                        if m:
                            return m.group(1)
            return None
        assert _cust_clause_origin(bypass) == flip, (knob, "bypass must flip the customer clause")
        assert _cust_clause_origin(no_op) == pre, (knob, "no_op must hold the customer clause")


def test_origin_code_bypass_relocates_med_not_removed():
    """audit-M4: the bypass must NOT delete the MED. The `set metric <m>` lives in the
    REDIST_CUST route-map PRE *and* POST (the decisive edit touches only the prefix-list seq
    and the `set origin` token), so the advertised MED is preserved across the ORIGIN flip."""
    mod = generator_origin_code
    for spec in mod.enumerate_specs():
        if spec.effect != "bypass":
            continue
        scn = mod.generate_origin_code_instance(600, spec=spec)
        post = scn.post_configs()[scn.change_target]
        med = "200" if spec.knob == "way_to_incomplete" else "50"
        assert f"set metric {med}" in post, (spec.dims_label(), "MED was removed, not relocated")
