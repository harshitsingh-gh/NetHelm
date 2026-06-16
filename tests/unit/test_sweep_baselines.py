"""Unit tests for the sweep baselines + scenario-level aggregator (synthetic, no
Batfish, no API). Covers the two NEW baselines (naive_count, modal_by_class), the
keyset grader's equivalence to grade_extended on the shared types, and the two-stage
(scenario-level, NOT pooled) aggregation."""

import math

from netbrace.reporting import baselines as bl
from netbrace.reporting.baselines import (
    grade_keysets,
    modal_keysets_by_class,
    naive_count_keysets,
    naive_session_loss_keysets,
    scenario_class,
)
from netbrace.reporting.sweep_aggregate import (
    aggregate_scenario_level,
    per_instance_means,
    population_stats,
)


# --------------------------------------------------------------------------- #
# Keyset grader mirrors grade_extended (shared arithmetic).
# --------------------------------------------------------------------------- #
def test_grade_keysets_exact_match_is_pass():
    truth = bl.empty_keysets()
    truth["prefixes"] = {"route|node=r2|vrf=default|prefix=203.0.113.0/24"}
    sr = grade_keysets(dict(truth), truth)
    assert sr.status == "pass"
    assert sr.exact_match is True
    assert sr.macro_f1 == 1.0


def test_grade_keysets_empty_vs_empty_is_vacuous_pass():
    sr = grade_keysets(bl.empty_keysets(), bl.empty_keysets())
    assert sr.macro_f1 == 1.0
    assert sr.false_session_alarm is False


def test_grade_keysets_false_session_alarm_fires():
    truth = bl.empty_keysets()
    truth["prefixes"] = {"route|node=r2|vrf=default|prefix=203.0.113.0/24"}
    pred = bl.empty_keysets()
    pred["sessions"] = {"bgp|vrf=default|node=r1|peer_ip=0.0.0.0"}
    sr = grade_keysets(pred, truth, is_trap=True)
    assert sr.false_session_alarm is True


# --------------------------------------------------------------------------- #
# naive_session_loss: pure false alarm on a trap (sessions stay up).
# --------------------------------------------------------------------------- #
def test_naive_session_loss_trips_fsa_and_scores_zero():
    truth = bl.empty_keysets()
    truth["prefixes"] = {"route|node=r2|vrf=default|prefix=203.0.113.0/24"}
    truth["reachability"] = {"reach|src=r2|dst=203.0.113.0/24|vrf=default"}
    pred = naive_session_loss_keysets("r1")
    sr = grade_keysets(pred, truth, is_trap=True)
    assert sr.false_session_alarm is True
    assert sr.macro_f1 == 0.0  # zero on every active dim (D1 FP + D2/D3 misses)


# --------------------------------------------------------------------------- #
# naive_count: gets direct effects, misses second-order.
# --------------------------------------------------------------------------- #
def test_naive_count_gets_direct_misses_second_order():
    cust = "203.0.113.0/24"
    truth = bl.empty_keysets()
    # direct effect on the change target r2 + a SECOND-ORDER effect on r3 + D9.
    truth["prefixes"] = {
        f"route|node=r2|vrf=default|prefix={cust}",
        f"route|node=r3|vrf=default|prefix={cust}",
    }
    truth["bgp_withdrawn"] = {f"bgp_withdrawn|node=r2|vrf=default|network={cust}"}
    pred = naive_count_keysets("r2", cust)
    sr = grade_keysets(pred, truth)
    # got the r2 prefix (direct) but missed r3 (second-order) and D9 entirely.
    assert sr.per_type["prefixes"].tp == 1
    assert sr.per_type["prefixes"].fn == 1
    assert sr.per_type["bgp_withdrawn"].f1 == 0.0
    assert 0.0 < sr.macro_f1 < 1.0


def test_naive_count_empty_when_no_named_prefix():
    assert naive_count_keysets("r1", None) == bl.empty_keysets()


# --------------------------------------------------------------------------- #
# scenario_class: derived without editing scenarios.py.
# --------------------------------------------------------------------------- #
def test_scenario_class_templated_strips_seed():
    a = scenario_class("gen_ipc_k2-one-out-plain-implicit_s0", "templated")
    b = scenario_class("gen_ipc_k2-one-out-plain-implicit_s41", "templated")
    assert a == b == "templated:k2-one-out-plain-implicit"


def test_scenario_class_grounded_uses_name():
    assert scenario_class("ipc3", "handauthored") == "handauthored:ipc3"


# --------------------------------------------------------------------------- #
# modal_by_class: majority element set per class; below ceiling when randomized.
# --------------------------------------------------------------------------- #
def test_modal_by_class_majority_only():
    # class C: 3 instances. Key K appears in 2/3 (majority -> modal); key R in 1/3.
    truth = {
        "i1": {**bl.empty_keysets(), "prefixes": {"K"}},
        "i2": {**bl.empty_keysets(), "prefixes": {"K"}},
        "i3": {**bl.empty_keysets(), "prefixes": {"R"}},
    }
    cls = {"i1": "C", "i2": "C", "i3": "C"}
    modal = modal_keysets_by_class(truth, cls)
    assert modal["C"]["prefixes"] == {"K"}  # R excluded (1/3, not majority)


def test_modal_by_class_below_ceiling_when_fully_randomized():
    # each instance of class C has a UNIQUE prefix (randomized) -> no majority key ->
    # modal is empty -> scores ~0 against any instance, well below the oracle ceiling.
    truth = {
        f"i{n}": {**bl.empty_keysets(), "prefixes": {f"route|p{n}"}}
        for n in range(5)
    }
    cls = {k: "C" for k in truth}
    modal = modal_keysets_by_class(truth, cls)
    assert modal["C"]["prefixes"] == set()
    for inst, gt in truth.items():
        modal_sr = grade_keysets(modal["C"], gt)
        ceiling_sr = grade_keysets(gt, gt)
        assert modal_sr.macro_f1 < ceiling_sr.macro_f1
        assert ceiling_sr.macro_f1 == 1.0


# --------------------------------------------------------------------------- #
# Two-stage aggregation: scenario-level, NOT pooled-i.i.d.
# --------------------------------------------------------------------------- #
def _rec(f1: float, fsa: bool = False, dim: str = "prefixes"):
    return {
        "macro_f1": f1, "micro_f1": f1,
        "per_type": {dim: {"f1": f1, "tp": 0, "fp": 0, "fn": 0,
                           "precision": f1, "recall": f1}},
        "active_types": [dim],
        "false_session_alarm": fsa,
        "valid_prediction": True,
    }


def test_per_instance_mean_collapses_samples():
    samples = {"i1": [_rec(1.0), _rec(0.0)]}  # mean = 0.5
    pim = per_instance_means(samples)
    assert pim["i1"]["macro_f1"] == 0.5
    assert pim["i1"]["per_dim_f1"]["prefixes"] == 0.5


def test_population_std_is_across_instances_not_pooled():
    # Two instances: i1 always 1.0 (2 samples), i2 always 0.0 (2 samples).
    # POOLED over 4 i.i.d. samples -> std of {1,1,0,0} = 0.5.
    # SCENARIO-LEVEL -> instance means {1.0, 0.0}; population std = 0.5 as well here,
    # but the MEAN is the mean of instance means (0.5), and n_instances=2 (not 4).
    samples = {"i1": [_rec(1.0), _rec(1.0)], "i2": [_rec(0.0), _rec(0.0)]}
    pop = population_stats(per_instance_means(samples))
    assert pop["n_instances"] == 2  # NOT 4 -> proves we did not pool samples
    assert pop["macro_f1"]["mean"] == 0.5
    # population std across the two instance means {1.0, 0.0}
    assert math.isclose(pop["macro_f1"]["std"], 0.5, abs_tol=1e-9)
    # SEM = std / sqrt(2)  (reported rounded to 6 dp)
    assert math.isclose(pop["macro_f1"]["sem"], 0.5 / math.sqrt(2), abs_tol=1e-6)


def test_aggregation_distinguishes_unequal_sample_counts_per_instance():
    # i1 has 4 samples, i2 has 2 — scenario-level weights each instance EQUALLY
    # (mean of means), not by sample count, so i1's extra samples do not dominate.
    samples = {
        "i1": [_rec(1.0)] * 4,
        "i2": [_rec(0.0)] * 2,
    }
    pop = aggregate_scenario_level(samples)
    assert pop["macro_f1"]["mean"] == 0.5  # (1.0 + 0.0)/2, NOT (4*1+2*0)/6=0.67
    assert pop["n_instances"] == 2


def test_fsa_rate_is_per_instance_then_population():
    # i1: 1 of 2 samples false-alarm (rate 0.5); i2: 0 of 2 (rate 0.0).
    samples = {
        "i1": [_rec(0.0, fsa=True), _rec(0.0, fsa=False)],
        "i2": [_rec(1.0, fsa=False), _rec(1.0, fsa=False)],
    }
    pop = aggregate_scenario_level(samples)
    assert pop["false_session_alarm_rate"]["mean"] == 0.25  # (0.5 + 0.0)/2
