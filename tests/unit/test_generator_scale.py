"""Unit tests for the Class-8 SCALE / DE-AGGREGATION-OVERFLOW generator
(``netbrace.tasks.safety.generator_scale``).

These are PURE tests (no live Batfish): they verify the generator's structural
contract — the six margin × supernet_fate combos produce the right GROUND-TRUTH
STRUCTURE (budget vs derived route count; supernet fate -> D2 watch set), the
patches round-trip, prose-hygiene holds (no specifics count / no outcome in
prose), and the instances are deterministic + seed-reproducible. The D8 threshold
arithmetic is exercised against the SAME stubbed-route-count oracle the
hand-authored scale_deagg test uses, so the count-vs-budget logic is checked
without a Batfish dependency.

The LIVE ground truth (D1=∅, D2 matches supernet_fate, D8 fires exactly per the
margin at the right node/resource, exact route counts: over_marginal == budget+1,
under < budget AND > pre) is verified against pinned Batfish in the generator
build/verify harness (reported with the generator); these tests assert the
structural invariants those live checks depend on.
"""

from __future__ import annotations

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.tasks.safety import generator_scale as gen
from netbrace.tasks.safety.generator_scale import (
    _EDGE_FIXED_ROUTES,
    ScaleSpec,
    all_combos,
    enumerable_count,
    enumerate_specs,
    generate_scale_deagg,
    generate_scale_suite,
)
from netbrace.topology.patches import apply_unified_diff


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _label(scn):
    return scn.name.split("gen_scale_")[1].rsplit("_s", 1)[0]


def _margin_fate(scn):
    return _label(scn).split("-")


def _expected_post_count(scn) -> int:
    """The edge POST installed-route count the generator's arithmetic targets:
    fixed routes + n_specifics (counted from the diff) + 1 iff the supernet kept."""
    post_up = scn.post_configs()[scn.change_target]
    n_spec = sum(
        1 for ln in post_up.splitlines()
        if ln.strip().startswith("network ") and ln.strip().endswith("/24")
    )
    margin, fate = _margin_fate(scn)
    kept_extra = 1 if fate == "kept" else 0
    return _EDGE_FIXED_ROUTES + n_spec + kept_extra


def _budget(scn) -> int:
    edge = scn.nodes[1]
    return scn.resource_limits[edge]["fib"]


def _oracle_with_count(node_count: dict[str, int]) -> ExtendedOracle:
    """An ExtendedOracle whose POST per-node route count is canned (no Batfish)."""
    o = ExtendedOracle.__new__(ExtendedOracle)
    o._installed_route_count = lambda snap, node: node_count[node]  # type: ignore
    return o


# --------------------------------------------------------------------------- #
# Axis space
# --------------------------------------------------------------------------- #
def test_enumerates_exactly_six_combos():
    specs = enumerate_specs()
    assert len(specs) == 6
    assert enumerable_count() == 6
    labels = {f"{s.margin}-{s.supernet_fate}" for s in specs}
    assert labels == {
        "over_clear-withdrawn", "over_clear-kept",
        "over_marginal-withdrawn", "over_marginal-kept",
        "under-withdrawn", "under-kept",
    }


def test_all_combos_returns_one_per_structure_distinct_seeds():
    combos = all_combos(seed=100)
    assert len(combos) == 6
    # one per structure
    assert {_label(s) for s in combos} == {
        "over_clear-withdrawn", "over_clear-kept",
        "over_marginal-withdrawn", "over_marginal-kept",
        "under-withdrawn", "under-kept",
    }
    # distinct seeds embedded in the names => distinct numbering across combos
    seeds = {s.name.rsplit("_s", 1)[1] for s in combos}
    assert len(seeds) == 6
    # unique ids
    assert len({s.name for s in combos}) == 6


# --------------------------------------------------------------------------- #
# Provenance + opt-in dimensions
# --------------------------------------------------------------------------- #
def test_all_instances_are_templated_traps_with_only_d8_d2_opt_ins():
    for scn in all_combos(seed=7):
        assert scn.provenance == "templated"
        # is_trap doctrine (red-team freeze gate 2026-06-10 #4, mirrors
        # generator_lp): under-kept has an EMPTY GT by construction — a
        # calibration CONTROL, never a damage trap. All other combos are traps.
        label = scn.name[len("gen_scale_"):].rsplit("_s", 1)[0]
        assert scn.is_trap is (label != "under-kept"), label
        assert scn.nodes[0] == scn.change_target  # upstream is the change target
        # D8 is opt-in via resource_limits; ONLY the edge carries a budget.
        edge = scn.nodes[1]
        assert set(scn.resource_limits) == {edge}
        assert set(scn.resource_limits[edge]) == {"fib"}
        # the scale class does not use D9/D10/waypoint/redundancy/forwarding intents
        assert scn.bgp_watch_prefixes == []
        assert scn.intent_invariants == []
        assert scn.waypoint_intents == []
        assert scn.redundancy_targets == []
        assert scn.forwarding_flows == []
        assert scn.reachability_flows == []


# --------------------------------------------------------------------------- #
# Round-trip + structural correctness of the de-aggregation edit
# --------------------------------------------------------------------------- #
def test_patch_round_trips_on_upstream_only():
    for scn in all_combos(seed=11):
        pre, post = scn.pre_configs, scn.post_configs()
        changed = [n for n in scn.nodes if post[n] != pre[n]]
        assert changed == [scn.change_target]  # only the upstream is edited
        assert apply_unified_diff(pre[scn.change_target], scn.patch) == \
            post[scn.change_target]
        # the edge is never config-edited (the flood arrives via BGP)
        assert post[scn.nodes[1]] == pre[scn.nodes[1]]


def test_baseline_originates_only_one_covering_supernet():
    for scn in all_combos(seed=12):
        pre_up = scn.pre_configs[scn.change_target]
        nets = [ln.strip() for ln in pre_up.splitlines()
                if ln.strip().startswith("network ")]
        # the upstream's own loopback /32 + the single covering /16, nothing else
        slash16 = [n for n in nets if n.endswith("/16")]
        slash24 = [n for n in nets if n.endswith("/24")]
        assert len(slash16) == 1
        assert slash24 == []


def test_post_structure_matches_supernet_fate():
    for scn in all_combos(seed=13):
        margin, fate = _margin_fate(scn)
        post_up = scn.post_configs()[scn.change_target]
        nets = [ln.strip() for ln in post_up.splitlines()
                if ln.strip().startswith("network ")]
        slash16 = [n for n in nets if n.endswith("/16")]
        slash24 = [n for n in nets if n.endswith("/24")]
        # de-aggregation ALWAYS adds the /24 specifics (never a no-op)
        assert len(slash24) >= 2
        # each specific is backed by its own discard static (so BGP can source it)
        for net in slash24:
            prefix = net.split()[1]
            assert f"ip route {prefix} blackhole" in post_up
        if fate == "withdrawn":
            assert slash16 == []  # the supernet origination + static are dropped
            sup = [ln for ln in scn.pre_configs[scn.change_target].splitlines()
                   if ln.strip().endswith("/16")][0].split()[1]
            assert f"network {sup}" not in post_up
            assert f"ip route {sup} blackhole" not in post_up
        else:  # kept
            assert len(slash16) == 1  # the supernet stays advertised alongside


# --------------------------------------------------------------------------- #
# Margin arithmetic (budget vs the derived post count) — the D8 discriminator
# --------------------------------------------------------------------------- #
def test_margin_budget_relationship_holds_per_class():
    for scn in all_combos(seed=14):
        margin, _fate = _margin_fate(scn)
        post = _expected_post_count(scn)
        budget = _budget(scn)
        pre_count = _EDGE_FIXED_ROUTES + 1  # baseline: fixed + the one supernet
        # the BASELINE must never already overflow (budget strictly above pre count)
        assert budget > pre_count
        if margin == "over_clear":
            assert post > budget
            assert post - budget >= 3  # comfortable margin
        elif margin == "over_marginal":
            assert post == budget + 1  # exceeds by EXACTLY one
        else:  # under
            assert post < budget  # stays below the budget => D8 must NOT fire
            assert post > pre_count  # but the specifics ARE added (not a no-op)


def test_d8_threshold_fires_exactly_per_margin_via_stub_oracle():
    """The count-vs-budget logic (the actual oracle path) on the GENERATOR's own
    derived counts: over_* fires, under stays silent — no Batfish needed."""
    for scn in all_combos(seed=15):
        margin, _ = _margin_fate(scn)
        edge = scn.nodes[1]
        post = _expected_post_count(scn)
        out = _oracle_with_count({edge: post})._scale_violations(scn.resource_limits)
        fired = [(e.node, e.resource) for e in out]
        if margin in ("over_clear", "over_marginal"):
            assert fired == [(edge, "fib")], scn.name
        else:
            assert fired == [], scn.name


def test_marginal_is_genuinely_off_by_one_not_robust_slack():
    """The over_marginal class is the precise-counting trap: bumping the budget by
    one (i.e. a model that miscounts the specifics by one) flips the verdict."""
    for scn in all_combos(seed=16):
        margin, _ = _margin_fate(scn)
        if margin != "over_marginal":
            continue
        edge = scn.nodes[1]
        post = _expected_post_count(scn)
        budget = _budget(scn)
        # at the true budget it fires (post == budget+1 > budget)
        assert _oracle_with_count({edge: post})._scale_violations(
            {edge: {"fib": budget}})
        # if the model had counted ONE fewer specific, post would == budget -> silent
        assert _oracle_with_count({edge: post - 1})._scale_violations(
            {edge: {"fib": budget}}) == []


# --------------------------------------------------------------------------- #
# Watch-set honesty (no gerrymander)
# --------------------------------------------------------------------------- #
def test_watch_set_is_honest_supernet_plus_sample_of_specifics():
    for scn in all_combos(seed=17):
        post_up = scn.post_configs()[scn.change_target]
        sup = [ln.strip().split()[1] for ln in scn.pre_configs[scn.change_target]
               .splitlines() if ln.strip().startswith("network ")
               and ln.strip().endswith("/16")][0]
        watched = set(scn.watched_prefixes)
        # the supernet IS watched (so its withdrawal is scored honestly)
        assert sup in watched
        # loopbacks are watched (negative controls)
        assert f"{scn.nodes[0]}".__class__  # placeholder; check by /32 membership
        assert sum(1 for w in watched if w.endswith("/32")) == 2
        # a SAMPLE of REAL specifics is watched (they are ADDED, never lost, so they
        # stay out of D2 — that is what makes the watch set non-gerrymandered)
        sampled = [w for w in watched if w.endswith("/24")]
        assert len(sampled) >= 1
        for s in sampled:
            assert f"network {s}" in post_up  # each watched /24 is a REAL origination


# --------------------------------------------------------------------------- #
# Prompt hygiene — the count / outcome must NEVER appear in prose
# --------------------------------------------------------------------------- #
def test_prose_never_states_specifics_count_or_outcome():
    for scn in all_combos(seed=18):
        margin, fate = _margin_fate(scn)
        post = _expected_post_count(scn)
        n_spec = post - _EDGE_FIXED_ROUTES - (1 if fate == "kept" else 0)
        prose = (scn.description + " " + scn.intents_text).lower()
        # the specifics COUNT must not appear as a literal in prose
        assert str(n_spec) not in prose, f"{scn.name}: specifics count leaked"
        # the outcome must not be stated (no overflow/exceed/violation verdicts)
        for banned in ("overflow", "exceed", "violat", "over budget",
                       "too many", "crosses", "blast"):
            assert banned not in prose, f"{scn.name}: outcome word '{banned}' leaked"
        # the budget annotation IS allowed (it is stated, honest known context)
        assert str(_budget(scn)) in scn.intents_text


def test_prose_is_margin_invisible():
    """over vs under must be indistinguishable from prose STYLE: the description
    template depends ONLY on supernet_fate, never on the margin class.

    Verified two ways: (1) no margin-class token ever appears in prose, and (2)
    holding supernet_fate fixed, the prose skeleton (with the per-instance literals
    — node names, ASN, prefixes, the stated budget — masked) is identical across all
    three margins. To isolate the margin axis we keep node names/addressing constant
    by drawing each margin at the SAME seed (only the budget/count differ)."""
    import re

    # (1) no margin-class word leaks into any prose
    for scn in all_combos(seed=19):
        prose = (scn.description + " " + scn.intents_text).lower()
        for tok in ("marginal", "over_clear", "under", "comfortabl", "barely",
                    "exactly one", "by one"):
            assert tok not in prose, f"{scn.name}: margin token '{tok}' leaked"

    # (2) skeleton invariance across margins for a fixed supernet_fate. Masking the
    # legitimate per-instance literals leaves only the template; it must be identical
    # for all three margins. Word-boundary-safe node masking (avoid clobbering
    # substrings like 'aggregate'); we draw each margin at the same seed so the node
    # names + addressing are identical and only the budget number differs.
    def _skeleton(scn):
        up, edge = scn.nodes
        txt = scn.description + "||" + scn.intents_text
        txt = re.sub(r"\b" + re.escape(up) + r"\b", "UP", txt)
        txt = re.sub(r"\b" + re.escape(edge) + r"\b", "EDGE", txt)
        txt = re.sub(r"AS\d+", "ASN", txt)
        txt = re.sub(r"\d+\.\d+\.\d+\.\d+/\d+", "PFX", txt)
        txt = re.sub(r"ceiling of \d+", "ceiling of N", txt)
        return txt

    for fate in ("withdrawn", "kept"):
        skeletons = {
            _skeleton(generate_scale_deagg(900, spec=ScaleSpec(m, fate)))
            for m in ("over_clear", "over_marginal", "under")
        }
        assert len(skeletons) == 1, f"margin leaks via prose for fate={fate}"


# --------------------------------------------------------------------------- #
# Determinism + seed reproducibility
# --------------------------------------------------------------------------- #
def test_same_seed_same_spec_is_byte_identical():
    spec = ScaleSpec("over_marginal", "withdrawn")
    a = generate_scale_deagg(123, spec=spec)
    b = generate_scale_deagg(123, spec=spec)
    assert a.name == b.name
    assert a.pre_configs == b.pre_configs
    assert a.post_configs() == b.post_configs()
    assert a.patch == b.patch
    assert a.watched_prefixes == b.watched_prefixes
    assert a.resource_limits == b.resource_limits
    assert a.description == b.description
    assert a.intents_text == b.intents_text


def test_different_seeds_give_distinct_numbering_same_structure():
    spec = ScaleSpec("over_clear", "kept")
    a = generate_scale_deagg(1, spec=spec)
    b = generate_scale_deagg(2, spec=spec)
    # SAME structural label, DIFFERENT randomized numbering (contamination control)
    assert _label(a) == _label(b) == "over_clear-kept"
    assert a.name != b.name
    # at least one of asn/addressing/names/supernet differs
    assert (a.pre_configs != b.pre_configs) or (a.watched_prefixes != b.watched_prefixes)


def test_bare_seed_walks_the_axis_space():
    # generate_scale_deagg(seed) with no spec picks a spec deterministically by seed
    labels = {_label(generate_scale_deagg(s)) for s in range(12)}
    assert labels == {
        "over_clear-withdrawn", "over_clear-kept",
        "over_marginal-withdrawn", "over_marginal-kept",
        "under-withdrawn", "under-kept",
    }


def test_suite_has_unique_ids_and_covers_axes():
    suite = generate_scale_suite(12, seed=500)
    assert len(suite) == 12
    assert len({s.name for s in suite}) == 12  # unique ids
    # the first 6 cover every structure once
    assert {_label(s) for s in suite[:6]} == {
        "over_clear-withdrawn", "over_clear-kept",
        "over_marginal-withdrawn", "over_marginal-kept",
        "under-withdrawn", "under-kept",
    }


def test_randomized_asns_avoid_handauthored_family_and_are_distinct():
    for scn in all_combos(seed=42):
        up = scn.pre_configs[scn.nodes[0]]
        edge = scn.pre_configs[scn.nodes[1]]
        up_asn = int([ln for ln in up.splitlines()
                      if ln.startswith("router bgp ")][0].split()[2])
        edge_asn = int([ln for ln in edge.splitlines()
                        if ln.startswith("router bgp ")][0].split()[2])
        # private 4-byte range, clear of the 65010/65020 hand-authored family
        assert up_asn >= 4_200_000_000
        assert edge_asn >= 4_200_000_000
        # eBGP: the two ASNs differ
        assert up_asn != edge_asn
