"""Tests for D8 ``ScaleViolation`` — the scale/resource-overflow class — and the
``scale_deagg`` de-aggregation scenario.

No live Batfish needed here:
  * the typed element key / round-trip through the fake model + parser are pure;
  * the oracle ``_scale_violations`` set/threshold logic is exercised via a stub
    that injects a canned per-node route count, so the count-vs-limit arithmetic
    is tested deterministically (over budget => fires; under budget => silent)
    without a Batfish dependency;
  * the live ``_installed_route_count`` query and the full ground truth (D1=∅,
    D2 prefixes_lost={(edge, 100.64.0.0/16)} — the supernet is honestly withdrawn —
    D3=∅, D8 fires) are verified by
    scripts/run_extended_scenario.py --scenario scale_deagg (the sanity gate).
"""

from __future__ import annotations

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import (
    EXT_ELEMENT_TYPES,
    ExtendedBlastRadius,
    ScaleViolation,
)
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel
from netbrace.tasks.safety import baseline_scale_deagg as base
from netbrace.tasks.safety import scenario_scale_deagg as sc
from netbrace.tasks.safety import scenarios
from netbrace.topology.patches import apply_unified_diff


# --------------------------------------------------------------------------- #
# The typed element — key omits the live count (determinism / grading)
# --------------------------------------------------------------------------- #
def test_scale_violation_key_canonicalizes_and_omits_count():
    a = ScaleViolation(node="Edge", resource="fib", limit=20, observed=44)
    b = ScaleViolation(node="edge", resource="fib", limit=999, observed=1)
    # The key is the violated (node, resource) ONLY — NOT the count/limit, so the
    # ground truth is stable and set-grading is deterministic.
    assert a.key == b.key
    assert a.key == "scale|node=edge|resource=fib"


def test_scale_is_a_graded_type():
    assert "scale" in EXT_ELEMENT_TYPES
    ks = ExtendedBlastRadius(
        scale_violations=[ScaleViolation(node="edge", resource="fib", limit=20, observed=44)]
    ).key_sets()
    assert ks["scale"] == {"scale|node=edge|resource=fib"}
    assert not ExtendedBlastRadius(
        scale_violations=[ScaleViolation(node="edge", resource="fib")]
    ).is_empty()


# --------------------------------------------------------------------------- #
# Parser + fake-model round trip (so the full pipeline scores D8 -> macro_f1=1.0)
# --------------------------------------------------------------------------- #
def test_d8_round_trips_through_fake_model_and_parser():
    truth = ExtendedBlastRadius(
        scale_violations=[ScaleViolation(node="edge", resource="fib", limit=20, observed=44)]
    )
    raw = ExtendedFakeModel("oracle").respond(truth)
    pred = parse_extended_prediction(raw)
    sr = grade_extended(pred, truth, task_id="t")
    assert sr.exact_match is True
    assert sr.per_type["scale"].f1 == 1.0
    assert "scale" in sr.active_types


# --------------------------------------------------------------------------- #
# Oracle threshold logic (stubbed per-node route count — no Batfish)
# --------------------------------------------------------------------------- #
def _oracle_with_count(node_count: dict[str, int]) -> ExtendedOracle:
    """An ExtendedOracle whose POST per-node route count is canned (no Batfish)."""
    o = ExtendedOracle.__new__(ExtendedOracle)  # bypass __init__ (no pybatfish)
    o._installed_route_count = lambda snap, node: node_count[node]  # type: ignore
    return o


def test_scale_fires_when_over_budget():
    o = _oracle_with_count({"edge": 44})
    out = o._scale_violations({"edge": {"fib": 20}})
    assert [(e.node, e.resource, e.limit, e.observed) for e in out] == [
        ("edge", "fib", 20, 44)
    ]


def test_scale_silent_when_under_budget_control():
    # The control: under budget => NO violation (count <= limit, incl. equality).
    assert _oracle_with_count({"edge": 5})._scale_violations({"edge": {"fib": 20}}) == []
    assert _oracle_with_count({"edge": 20})._scale_violations({"edge": {"fib": 20}}) == []
    # empty budget => D8 disabled (opt-in)
    assert _oracle_with_count({"edge": 999})._scale_violations({}) == []
    assert _oracle_with_count({"edge": 999})._scale_violations(None) == []


def test_rib_proxy_also_scored():
    # The route-count proxy is valid for BOTH fib and rib.
    out = _oracle_with_count({"edge": 44})._scale_violations({"edge": {"rib": 20}})
    assert [(e.node, e.resource) for e in out] == [("edge", "rib")]


def test_label_and_acl_tcam_NOT_scored_by_route_count():
    """Red-team fix: the IPv4 route count must NOT fire a label (MPLS) or acl_tcam
    budget — that is a category error. Those resources are skipped entirely."""
    o = _oracle_with_count({"edge": 9999})  # huge count: would trip any numeric limit
    # A label budget alone => no violation (route count is not an LFIB depth).
    assert o._scale_violations({"edge": {"label": 1}}) == []
    # An acl_tcam budget alone => no violation (route count is not a TCAM count).
    assert o._scale_violations({"edge": {"acl_tcam": 1}}) == []
    # MIXED: fib fires, but label/acl_tcam on the same node are still skipped.
    out = o._scale_violations({"edge": {"fib": 20, "label": 1, "acl_tcam": 1}})
    assert sorted((e.node, e.resource) for e in out) == [("edge", "fib")]


def test_route_count_not_queried_when_no_fib_rib_resource(monkeypatch):
    """When a node declares ONLY non-proxy resources, the (potentially expensive)
    route count is not even computed for it."""
    o = ExtendedOracle.__new__(ExtendedOracle)
    calls = []

    def _counter(snap, node):
        calls.append(node)
        return 9999

    o._installed_route_count = _counter  # type: ignore
    assert o._scale_violations({"edge": {"label": 1, "acl_tcam": 1}}) == []
    assert calls == []  # never queried -> no fan-out against label/acl_tcam


# --------------------------------------------------------------------------- #
# The scenario (pure structure — no Batfish)
# --------------------------------------------------------------------------- #
def test_registered_and_carries_budget():
    assert "scale_deagg" in scenarios.REGISTRY
    scn = scenarios.build("scale_deagg")
    assert scn.change_target == "upstream"
    assert set(scn.nodes) == {"upstream", "edge"}
    # ONLY the edge carries a FIB budget (the overflow victim); upstream is free.
    assert scn.resource_limits == {"edge": {"fib": sc.EDGE_FIB_BUDGET}}
    assert "upstream" not in scn.resource_limits


def test_existing_scenarios_have_no_resource_limits():
    """D8 is opt-in: every OTHER scenario keeps an empty resource_limits."""
    for name in scenarios.REGISTRY:
        if name == "scale_deagg":
            continue
        assert scenarios.build(name).resource_limits == {}


def test_patch_round_trips_on_upstream_only():
    scn = scenarios.build("scale_deagg")
    pre, post = scn.pre_configs, scn.post_configs()
    changed = [n for n in scn.nodes if post[n] != pre[n]]
    assert changed == ["upstream"]
    assert apply_unified_diff(pre["upstream"], scn.patch) == post["upstream"]


def test_post_removes_summary_and_adds_more_specifics():
    post_up = scenarios.build("scale_deagg").post_configs()["upstream"]
    # the single covering /16 summary is GONE (origination + backing static)
    assert "network 100.64.0.0/16" not in post_up
    assert "ip route 100.64.0.0/16 blackhole" not in post_up
    # every more-specific /24 is now originated + backed by its own discard static
    for i in range(base.DEAGG_COUNT):
        assert f"network 100.64.{i}.0/24" in post_up
        assert f"ip route 100.64.{i}.0/24 blackhole" in post_up


def test_de_agg_adds_many_routes_not_loses_them():
    """Precondition for the thesis: the change ADDS routes (no D2 loss signal)."""
    scn = scenarios.build("scale_deagg")
    pre_up = scn.pre_configs["upstream"]
    post_up = scn.post_configs()["upstream"]
    pre_networks = [ln for ln in pre_up.splitlines() if ln.strip().startswith("network 100.64")]
    post_networks = [ln for ln in post_up.splitlines() if ln.strip().startswith("network 100.64")]
    # 1 summary -> DEAGG_COUNT more-specifics (a strict increase in originated routes)
    assert len(pre_networks) == 1
    assert len(post_networks) == base.DEAGG_COUNT
    assert base.DEAGG_COUNT > 1
    # the edge is untouched by the diff (the flood arrives via BGP, not a config edit)
    assert scn.post_configs()["edge"] == scn.pre_configs["edge"]


def test_budget_sits_between_baseline_and_post_origination():
    """Sanity on the budget choice: DEAGG_COUNT more-specifics comfortably exceed
    the budget, while the baseline originates only one block route."""
    assert sc.EDGE_FIB_BUDGET < base.DEAGG_COUNT  # post flood clears the budget
    assert sc.EDGE_FIB_BUDGET > 1                  # baseline (1 block route) is under


def test_budget_sweep_brackets_observed_counts():
    """Audit the budget placement against the PINNED live counts so it is not
    cherry-picked: the budget must sit in [BASELINE_EDGE_COUNT, POST_EDGE_COUNT)
    so it fires post-change and stays silent on the baseline. The exact live counts
    are re-verified by scripts/run_extended_scenario.py; here we assert the band
    relationship the comment documents."""
    assert sc.BASELINE_EDGE_COUNT <= sc.EDGE_FIB_BUDGET < sc.POST_EDGE_COUNT
    # The structural gap is ~DEAGG_COUNT-1 routes (one /16 removed, DEAGG_COUNT /24s
    # added), so the violation is robust to the exact budget within the band.
    assert sc.POST_EDGE_COUNT - sc.BASELINE_EDGE_COUNT >= base.DEAGG_COUNT - 1
    # The threshold logic itself: a stub at each pinned count confirms the band.
    fires = _oracle_with_count({"edge": sc.POST_EDGE_COUNT})._scale_violations(
        {"edge": {"fib": sc.EDGE_FIB_BUDGET}})
    silent = _oracle_with_count({"edge": sc.BASELINE_EDGE_COUNT})._scale_violations(
        {"edge": {"fib": sc.EDGE_FIB_BUDGET}})
    assert [e.resource for e in fires] == ["fib"]
    assert silent == []
