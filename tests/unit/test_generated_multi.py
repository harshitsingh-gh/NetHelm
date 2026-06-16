"""Wiring tests for the multi-mechanism templated split (audit 2026-06-10 K3):
build_generated_suite_multi interleaves all four generators, scenario_class
derives seed-free classes for every generator family, and fake_ground_truth has
a structural branch for each (so zero-API sweep validation covers them)."""

from netbrace.reporting.baselines import scenario_class
from netbrace.reporting.fake_oracle import fake_ground_truth
from netbrace.tasks.safety import scenarios


def _suite(n=24, seed=0):
    return scenarios.build_generated_suite_multi(n, base_seed=seed)


# --------------------------------------------------------------------------- #
# build_generated_suite_multi
# --------------------------------------------------------------------------- #
def test_multi_suite_spans_all_four_mechanisms():
    names = [s.name for s in _suite(24)]
    for fam in ("gen_ipc_", "gen_leak_", "gen_lp_", "gen_scale_"):
        assert sum(1 for n in names if n.startswith(fam)) == 6, fam


def test_multi_suite_exact_n_and_unique_names():
    for n in (1, 4, 7, 24):
        suite = _suite(n)
        assert len(suite) == n
        assert len({s.name for s in suite}) == n


def test_multi_suite_interleaves_prefix_coverage_early():
    # a truncated prefix (small --n-generated) must still span all mechanisms.
    fams = {s.name.split("_", 2)[1] for s in _suite(4)}
    assert fams == {"ipc", "leak", "lp", "scale"}


def test_multi_suite_seed_reproducible():
    a = [s.name for s in _suite(24, seed=5)]
    b = [s.name for s in _suite(24, seed=5)]
    c = [s.name for s in _suite(24, seed=6)]
    assert a == b
    assert a != c


def test_multi_suite_all_templated_provenance():
    assert all(s.provenance == "templated" for s in _suite(24))


# --------------------------------------------------------------------------- #
# scenario_class for the new families
# --------------------------------------------------------------------------- #
def test_scenario_class_strips_seed_for_all_families():
    for s in _suite(24, seed=3):
        cls = scenario_class(s.name, s.provenance)
        assert cls.startswith("templated:")
        assert "_s3" not in cls and "_s" + s.name.rsplit("_s", 1)[1] not in cls


def test_scenario_class_shared_across_seeds():
    # same structural combo, different seed -> same class (the modal-floor basis).
    a = scenario_class("gen_leak_ms_blackhole-low_half_s7", "templated")
    b = scenario_class("gen_leak_ms_blackhole-low_half_s99", "templated")
    assert a == b == "templated:leak_ms_blackhole-low_half"


def test_scenario_class_coarsen_noop_for_new_families():
    n = "gen_scale_over_clear-withdrawn_s7"
    assert scenario_class(n, "templated", coarsen=True) == \
        scenario_class(n, "templated", coarsen=False)


# --------------------------------------------------------------------------- #
# fake_ground_truth structural branches (D1 ALWAYS empty — the trap invariant)
# --------------------------------------------------------------------------- #
def _by_prefix(prefix, suite):
    return [s for s in suite if s.name.startswith(prefix)]


def test_fake_gt_d1_always_empty_all_families():
    for s in _suite(24):
        assert fake_ground_truth(s)["sessions"] == set(), s.name


def test_fake_gt_leak_blackhole_is_d3_d7_only():
    suite = _suite(24)
    s = next(x for x in suite if x.name.startswith("gen_leak_ms_blackhole"))
    ks = fake_ground_truth(s)
    assert ks["reachability"] and ks["forwarding"]
    assert not ks["prefixes"] and not ks["waypoint"] and not ks["intent"]


def test_fake_gt_leak_reroute_is_d4_d10_only():
    suite = _suite(24)
    s = next(x for x in suite if x.name.startswith("gen_leak_ms_reroute"))
    ks = fake_ground_truth(s)
    assert ks["waypoint"] and ks["intent"]
    assert not ks["reachability"] and not ks["forwarding"] and not ks["prefixes"]


def test_fake_gt_lp_bypass_is_d4_only():
    suite = _suite(24)
    s = next(x for x in suite if x.name.startswith("gen_lp_") and "-bypass" in x.name)
    ks = fake_ground_truth(s)
    assert ks["waypoint"]
    assert all(not v for k, v in ks.items() if k != "waypoint")


def test_fake_gt_lp_noop_is_completely_empty():
    suite = _suite(24)
    s = next(x for x in suite if x.name.startswith("gen_lp_") and "-no_op" in x.name)
    ks = fake_ground_truth(s)
    assert all(not v for v in ks.values())


def test_fake_gt_scale_margin_and_fate():
    # over_* -> D8 fires; under -> D8 silent; withdrawn -> supernet D2; kept -> no D2.
    from netbrace.tasks.safety.generator_scale import generate_scale_deagg, enumerate_specs
    for spec in enumerate_specs():
        s = generate_scale_deagg(7, spec)
        ks = fake_ground_truth(s)
        margin, fate = s.name[len("gen_scale_"):].rsplit("_s", 1)[0].split("-")
        assert bool(ks["scale"]) == margin.startswith("over"), s.name
        assert bool(ks["prefixes"]) == (fate == "withdrawn"), s.name


# --------------------------------------------------------------------------- #
# build_generated_suite_reroutes — the 13 quiet-reroute mechanism generators
# (wiring 2026-06-15: the templated split must also cover the silent-path-shift
# half; ONE round-robin builder enumerates all 13 with distinct seed bands so a
# truncated prefix spans every mechanism and no two generators collide names).
# --------------------------------------------------------------------------- #
_REROUTE_PREFIXES = tuple(p for (_m, _f, p) in scenarios.REROUTE_GENERATORS)


def _reroutes(n=52, seed=0, include_noop=True):
    return scenarios.build_generated_suite_reroutes(
        n, base_seed=seed, include_noop=include_noop)


def test_reroutes_constant_is_the_thirteen():
    assert len(scenarios.REROUTE_GENERATORS) == 13
    # each entry is (module_slug, suite_fn_name, name_prefix) and the function exists.
    import importlib
    for mod_slug, fn_name, prefix in scenarios.REROUTE_GENERATORS:
        mod = importlib.import_module(f"netbrace.tasks.safety.{mod_slug}")
        assert callable(getattr(mod, fn_name)), (mod_slug, fn_name)
        assert prefix.startswith("gen_") and prefix.endswith("_")


def test_reroutes_exact_n_and_unique_names():
    for n in (1, 13, 14, 26, 52, 130):
        suite = _reroutes(n)
        assert len(suite) == n, n
        assert len({s.name for s in suite}) == n, f"dup names at n={n}"


def test_reroutes_span_all_thirteen_prefixes():
    # at n=52 (4 per generator) every mechanism must appear.
    names = [s.name for s in _reroutes(52)]
    for p in _REROUTE_PREFIXES:
        assert any(nm.startswith(p) for nm in names), f"missing {p}"


def test_reroutes_truncated_prefix_spans_first_k_generators():
    # a small --n still spans distinct mechanisms (round-robin, one per gen up to k).
    suite = _reroutes(13)
    spanned = {p for p in _REROUTE_PREFIXES
               if any(s.name.startswith(p) for s in suite)}
    assert spanned == set(_REROUTE_PREFIXES)  # n=13 hits each generator exactly once


def test_reroutes_all_templated_provenance():
    assert all(s.provenance == "templated" for s in _reroutes(52))


def test_reroutes_is_trap_is_fifty_fifty_with_noop():
    # include_noop default -> balanced bypass:no_op (the anti-gaming calibration).
    # holds once every generator emits an even count (n=26 -> 2/gen, n=52 -> 4/gen).
    for n in (26, 52, 130):
        suite = _reroutes(n)
        n_trap = sum(1 for s in suite if s.is_trap)
        n_safe = sum(1 for s in suite if not s.is_trap)
        assert n_trap == n_safe == n // 2, (n, n_trap, n_safe)


def test_reroutes_include_noop_false_is_all_traps():
    suite = _reroutes(13, include_noop=False)
    assert all(s.is_trap for s in suite), [s.name for s in suite if not s.is_trap]


def test_reroutes_seed_reproducible_and_seed_sensitive():
    a = [s.name for s in _reroutes(52, seed=7)]
    b = [s.name for s in _reroutes(52, seed=7)]
    c = [s.name for s in _reroutes(52, seed=8)]
    assert a == b          # byte-identical for same base_seed
    assert a != c          # seed-sensitive (contamination control)


def test_reroutes_distinct_seed_bands_prevent_collisions():
    # the per-generator seed stride must keep names globally unique even at large n
    # (a shared seed across generators would produce colliding randomized octets).
    big = _reroutes(260)            # 20 per generator
    assert len({s.name for s in big}) == 260


# --------------------------------------------------------------------------- #
# fake_ground_truth — generic reroute branch (bypass -> {waypoint,intent}; no_op
# -> COMPLETELY empty; D1 always empty). Required for the offline --oracle fake gate.
# --------------------------------------------------------------------------- #
def test_fake_gt_reroute_bypass_is_waypoint_intent_only():
    suite = _reroutes(52)
    seen = set()
    for s in suite:
        if not s.is_trap:
            continue
        fam = next(p for p in _REROUTE_PREFIXES if s.name.startswith(p))
        seen.add(fam)
        ks = fake_ground_truth(s)
        nonempty = {k for k, v in ks.items() if v}
        assert nonempty == {"waypoint", "intent"}, (s.name, nonempty)
        assert ks["sessions"] == set()  # D1 always empty -> the trap invariant
    assert seen == set(_REROUTE_PREFIXES)  # exercised every family's bypass


def test_fake_gt_reroute_noop_is_completely_empty():
    suite = _reroutes(52)
    seen = set()
    for s in suite:
        if s.is_trap:
            continue
        fam = next(p for p in _REROUTE_PREFIXES if s.name.startswith(p))
        seen.add(fam)
        ks = fake_ground_truth(s)
        assert all(not v for v in ks.values()), (s.name, ks)
    assert seen == set(_REROUTE_PREFIXES)  # exercised every family's no_op


def test_fake_gt_reroute_keys_match_scenario_waypoint_intents():
    # the emitted waypoint/intent keys are derived from the scenario's own
    # waypoint_intents + intent_invariants (the live-oracle key shape), not literals.
    from netbrace.core.schemas import canon_node, canon_prefix
    s = next(x for x in _reroutes(52) if x.name.startswith("gen_rr_bestpath_") and x.is_trap)
    ks = fake_ground_truth(s)
    (src, dst, via) = s.waypoint_intents[0]
    assert ks["waypoint"] == {
        f"waypoint|src={canon_node(src)}|dst={canon_prefix(dst)}|via={canon_node(via)}|vrf=default"}
    inv = s.intent_invariants[0]
    assert ks["intent"] == {
        f"intent|kind={inv.kind}|src={canon_node(inv.src)}|dst={canon_prefix(inv.dst)}"}
