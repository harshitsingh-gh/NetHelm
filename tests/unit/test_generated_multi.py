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
