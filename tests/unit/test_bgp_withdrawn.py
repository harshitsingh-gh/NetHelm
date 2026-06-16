"""Tests for D9 ``BgpRouteWithdrawn`` — the control-plane discriminator (item 1 of
oracle_determinism_spec_v1.md) and the has-static Class-1 sibling.

No live Batfish needed here:
  * the new typed element / grader / parser round-trip are pure;
  * the oracle ``_bgp_withdrawn_diff`` is exercised via a stub that injects the
    live-verified BGP-RIB BEST sets, so the SET ARITHMETIC + scoping is tested
    deterministically without a Batfish dependency;
  * the live ``_bgp_rib_prefixes`` query (Status-list membership) and the full
    ground truth are verified by scripts/run_extended_scenario.py --scenario
    ipc_static (the sanity gate).
"""

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import (
    BgpRouteWithdrawn,
    EXT_ELEMENT_TYPES,
    ExtendedBlastRadius,
)
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel
from netbrace.tasks.safety import baseline_ipc3 as ipc
from netbrace.tasks.safety import scenario_ipc as sc
from netbrace.tasks.safety import scenarios
from netbrace.topology.patches import apply_unified_diff

CUSTOMER = ipc.CUSTOMER_PREFIX  # 203.0.113.0/24


# --------------------------------------------------------------------------- #
# The typed element
# --------------------------------------------------------------------------- #
def test_bgp_withdrawn_key_canonicalizes():
    a = BgpRouteWithdrawn(node="R2", network="203.0.113.0/24")
    b = BgpRouteWithdrawn(node="r2", network="203.0.113.0/24", vrf="default")
    assert a.key == b.key
    assert a.key == "bgp_withdrawn|node=r2|vrf=default|network=203.0.113.0/24"


def test_bgp_withdrawn_is_ninth_type():
    assert "bgp_withdrawn" in EXT_ELEMENT_TYPES
    ks = ExtendedBlastRadius(
        bgp_withdrawals=[BgpRouteWithdrawn(node="r2", network=CUSTOMER)]
    ).key_sets()
    assert ks["bgp_withdrawn"] == {"bgp_withdrawn|node=r2|vrf=default|network=203.0.113.0/24"}
    assert not ExtendedBlastRadius(
        bgp_withdrawals=[BgpRouteWithdrawn(node="r2", network=CUSTOMER)]
    ).is_empty()


# --------------------------------------------------------------------------- #
# Parser + fake-model round trip (so the full pipeline scores D9)
# --------------------------------------------------------------------------- #
def test_d9_round_trips_through_fake_model_and_parser():
    truth = ExtendedBlastRadius(
        bgp_withdrawals=[BgpRouteWithdrawn(node="r2", network=CUSTOMER)]
    )
    raw = ExtendedFakeModel("oracle").respond(truth)
    pred = parse_extended_prediction(raw)
    sr = grade_extended(pred, truth, task_id="t")
    assert sr.exact_match is True
    assert sr.per_type["bgp_withdrawn"].f1 == 1.0
    assert "bgp_withdrawn" in sr.active_types


# --------------------------------------------------------------------------- #
# The discriminator: sibling (D9 only) is NOT scored like a no-op
# --------------------------------------------------------------------------- #
def test_sibling_truth_is_control_plane_only_and_beats_noop():
    """has-static sibling ground truth: D9 fires; D1/D2/D3 silent (FIB+reach survive).

    A no-op / config-bug-that-did-nothing has an EMPTY ground truth. The grader
    must NOT score the sibling identically to that no-op: predicting "nothing"
    (the wrong answer for the sibling) fails, whereas it would pass for a true
    no-op. That separation is the whole point of the sibling.
    """
    sibling_truth = ExtendedBlastRadius(
        bgp_withdrawals=[BgpRouteWithdrawn(node="r2", network=CUSTOMER)]
    )
    assert sibling_truth.base.is_empty()           # D1/D2/D3 silent
    assert not sibling_truth.is_empty()            # but D9 fires

    # A model that predicts "nothing happens" (correct for a no-op) MISSES the sibling.
    empty_pred = parse_extended_prediction(ExtendedFakeModel("empty").respond(sibling_truth))
    sr_miss = grade_extended(empty_pred, sibling_truth, task_id="sibling_vs_empty")
    assert sr_miss.status == "fail"
    assert sr_miss.macro_f1 == 0.0

    # The same "nothing" prediction is CORRECT for a genuine no-op (empty truth).
    noop_truth = ExtendedBlastRadius()
    sr_noop = grade_extended(
        parse_extended_prediction(ExtendedFakeModel("empty").respond(noop_truth)),
        noop_truth, is_trap=True, task_id="true_noop",
    )
    assert sr_noop.status == "pass"
    # => the sibling and the no-op are NOT scored alike under the same prediction.


# --------------------------------------------------------------------------- #
# Oracle set arithmetic (stubbed BGP-RIB BEST sets — live-verified values)
# --------------------------------------------------------------------------- #
def _oracle_with_best(best_pre, best_post):
    """An ExtendedOracle whose BGP-RIB BEST queries return canned sets (no Batfish)."""
    o = ExtendedOracle.__new__(ExtendedOracle)  # bypass __init__ (no pybatfish needed)
    o._bgp_rib_prefixes = lambda snap: best_pre if snap == "pre" else best_post  # type: ignore
    return o


def test_bgp_withdrawn_diff_fires_on_lost_best_route():
    # Live-verified ipc_static values: r2's BEST customer route is the sole loss.
    pre = {("r1", "default", CUSTOMER), ("r2", "default", CUSTOMER), ("r3", "default", CUSTOMER)}
    post = {("r1", "default", CUSTOMER), ("r3", "default", CUSTOMER)}
    o = _oracle_with_best(pre, post)
    out = o._bgp_withdrawn_diff(list(ipc.WATCHED_PREFIXES))
    assert [(e.node, e.vrf, e.network) for e in out] == [("r2", "default", CUSTOMER)]


def test_bgp_withdrawn_diff_scoped_to_watched_and_empty_for_noop():
    pre = {("r2", "default", CUSTOMER)}
    # no change -> empty diff (a true no-op yields empty D9)
    assert _oracle_with_best(pre, pre)._bgp_withdrawn_diff(list(ipc.WATCHED_PREFIXES)) == []
    # withdrawal of an UNWATCHED prefix is not scored (transit/connected churn)
    pre2 = {("r2", "default", "198.51.100.0/24")}
    post2: set = set()
    assert _oracle_with_best(pre2, post2)._bgp_withdrawn_diff(list(ipc.WATCHED_PREFIXES)) == []
    # empty watch list -> D9 disabled (opt-in); S-IPC-01 path is untouched
    assert _oracle_with_best(pre, set())._bgp_withdrawn_diff([]) == []


# --------------------------------------------------------------------------- #
# The sibling scenario (pure structure — no Batfish)
# --------------------------------------------------------------------------- #
def test_sibling_registered_and_enables_d9_only():
    scn = scenarios.build("ipc_static")
    assert scn.name == "ipc3_static"
    assert CUSTOMER in scn.bgp_watch_prefixes          # D9 enabled here
    # the FLAGSHIP does NOT enable D9 -> its ground truth is unchanged
    assert scenarios.build("ipc").bgp_watch_prefixes == []


def test_sibling_adds_exactly_one_static_on_r2_only():
    base = ipc.baseline_configs()
    sib = ipc.baseline_configs_static()
    # r1 and r3 are byte-identical to the frozen baseline
    assert sib["r1"] == base["r1"]
    assert sib["r3"] == base["r3"]
    # r2 gains exactly the customer static backup, nothing else
    assert f"ip route {CUSTOMER} 192.0.2.1" in sib["r2"]
    assert f"ip route {CUSTOMER}" not in base["r2"]
    extra = [ln for ln in sib["r2"].splitlines() if ln not in base["r2"].splitlines()]
    assert extra == [f"ip route {CUSTOMER} 192.0.2.1"]
    # still no FRR access-list anywhere (determinism-spec constraint)
    for cfg in sib.values():
        assert "access-list" not in cfg


def test_sibling_patch_is_same_filter_and_round_trips():
    scn = scenarios.build("ipc_static")
    # same r1 change as S-IPC-01
    assert scn.patch == sc.change_patch()
    post = scn.post_configs()
    after_r1 = apply_unified_diff(scn.pre_configs["r1"], scn.patch)
    assert post["r1"] == after_r1
    assert "route-map TO_R2_OUT out" in post["r1"]
    # untargeted nodes unchanged (incl. r2's static)
    assert post["r2"] == scn.pre_configs["r2"]
    assert f"ip route {CUSTOMER} 192.0.2.1" in post["r2"]
