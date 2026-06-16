"""Unit test for the NON-GAMEABLE reroute detection metric
(``netbrace.reporting.sweep_aggregate.reroute_detection_scores``) and the
calibration-twin false-alarm bug fix on both graders.

This test is the HEADLINE deliverable: it CODIFIES that no constant / label-independent
predictor beats NetBrace-Detect = 0.50 / Youden_J = 0.0 on the quiet-reroute split,
while a perfect oracle scores 1.0 / 1.0 and a partial reasoner lands strictly between.

Everything is SYNTHETIC — no Batfish, no API, no saved artifacts. We build graded
sample records by hand (the same flat shape the sweep persists: per_type tp/fp/fn,
is_trap, instance, empty_truth_false_alarm) so the metric arithmetic is pinned in
isolation. We ALSO exercise the real graders to prove the bug fix
(empty_truth_false_alarm fires on the is_trap=False no_op twins, which the legacy
false_alarm could never reach).

The reroute twin contract (MEASURED, trusted):
  * BYPASS twin  : is_trap=True,  ground truth = {D4 waypoint, D10 intent} ONLY.
  * NO_OP twin   : is_trap=False, ground truth = COMPLETELY EMPTY (calibration).
"""

from __future__ import annotations

import math

import pytest

from netbrace.graders.extended import grade_extended
from netbrace.graders.semantic_sets import grade_keysets_semantic
from netbrace.reporting.baselines import empty_keysets, grade_keysets
from netbrace.reporting.sweep_aggregate import (
    REROUTE_TRUTH_DIMS,
    reroute_detection_scores,
    reroute_family_of,
)
from netbrace.core.dimensions import (
    ExtendedBlastRadius,
    IntentViolation,
    WaypointViolation,
)

# Three structurally-distinct reroute families, two instances each, N samples per
# instance — enough to exercise the two-stage (per-instance -> per-family -> pooled)
# reduction and the equal-family-weight headline.
FAMILIES = ("far_as_prepend", "community_lp", "rr_bestpath")
INSTANCES_PER_FAMILY = 2
N_SAMPLES = 5

# A canonical bypass ground truth: one waypoint element (D4) + one intent element (D10).
_WP_KEY = "waypoint|src=r1|dst=203.0.113.0/24|via=r4|vrf=default"
_INTENT_KEY = "intent|kind=waypoint|src=r1|dst=203.0.113.0/24"


def _bypass_truth() -> dict[str, set[str]]:
    t = empty_keysets()
    t["waypoint"] = {_WP_KEY}
    t["intent"] = {_INTENT_KEY}
    return t


def _noop_truth() -> dict[str, set[str]]:
    return empty_keysets()  # completely empty


# --------------------------------------------------------------------------- #
# Synthetic graded-record builder. Given a prediction's per-dim (tp, fp, fn) over the
# scored dims, emit the flat dict shape the sweep persists + the metric consumes.
# --------------------------------------------------------------------------- #
def _per_type(counts: dict[str, tuple[int, int, int]]) -> dict[str, dict]:
    pt: dict[str, dict] = {}
    for dim, (tp, fp, fn) in counts.items():
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        pt[dim] = {"tp": tp, "fp": fp, "fn": fn,
                   "precision": precision, "recall": recall, "f1": f1}
    return pt


def _rec(instance: str, *, is_trap: bool, counts: dict[str, tuple[int, int, int]]):
    """One graded sample record. ``empty_truth_false_alarm`` is computed the way the
    fixed grader does: truth_empty (no fn anywhere => no truth) AND a non-empty
    prediction (some tp+fp > 0)."""
    truth_empty = all(fn == 0 for (_tp, _fp, fn) in counts.values())
    pred_nonempty = any((tp + fp) > 0 for (tp, fp, _fn) in counts.values())
    return {
        "instance": instance,
        "is_trap": is_trap,
        "per_type": _per_type(counts),
        "empty_truth_false_alarm": truth_empty and pred_nonempty,
    }


# --------------------------------------------------------------------------- #
# Strategy predictors -> per-dim (tp, fp, fn) given the twin kind.
# Each returns counts over the dims that matter for the metric ({D4,D10} truth on
# bypass; FP-over-scored on no_op).
# --------------------------------------------------------------------------- #
def _counts_always_d4_d10(is_trap: bool) -> dict[str, tuple[int, int, int]]:
    """Always predict exactly {D4 waypoint, D10 intent} (the macro_f1_damage gamer)."""
    if is_trap:  # bypass: both truths present -> hit both (tp=1, fn=0)
        return {"waypoint": (1, 0, 0), "intent": (1, 0, 0)}
    # no_op: truth empty -> both predictions are pure false alarms (fp=1)
    return {"waypoint": (0, 1, 0), "intent": (0, 1, 0)}


def _counts_always_empty(is_trap: bool) -> dict[str, tuple[int, int, int]]:
    """Predict nothing at all (the always-empty / silent gamer)."""
    if is_trap:  # bypass: misses both truths (fn=1)
        return {"waypoint": (0, 0, 1), "intent": (0, 0, 1)}
    return {}  # no_op: nothing predicted, nothing true -> no false alarm


def _counts_perfect(is_trap: bool) -> dict[str, tuple[int, int, int]]:
    """The oracle: hit bypass truths exactly, predict nothing on no_op."""
    if is_trap:
        return {"waypoint": (1, 0, 0), "intent": (1, 0, 0)}
    return {}


def _counts_partial(is_trap: bool, *, fire: bool) -> dict[str, tuple[int, int, int]]:
    """A realistic reasoner: on a given instance it either fires (catches the bypass,
    but also false-alarms the matched no_op) or stays silent. ``fire`` toggles per
    instance so the population recall and FAR are both strictly in (0,1)."""
    if is_trap:
        if fire:  # caught D4 but missed D10 (recall-where-truth = 0.5 on this sample)
            return {"waypoint": (1, 0, 0), "intent": (0, 0, 1)}
        return {"waypoint": (0, 0, 1), "intent": (0, 0, 1)}  # missed both
    if fire:
        return {"waypoint": (0, 1, 0)}  # false-alarmed this no_op
    return {}  # correctly silent on this no_op


# --------------------------------------------------------------------------- #
# Build a balanced bypass/no_op record set for a strategy.
# --------------------------------------------------------------------------- #
def _build_records(counts_fn) -> list[dict]:
    """Balanced set: for every family, INSTANCES_PER_FAMILY bypass instances and the
    same number of no_op twins, N_SAMPLES samples each. ``counts_fn(is_trap, idx)``
    returns the per-dim counts for an instance index (idx lets the partial strategy
    alternate fire/silent across instances)."""
    recs: list[dict] = []
    for fam in FAMILIES:
        for idx in range(INSTANCES_PER_FAMILY):
            for is_trap in (True, False):
                kind = "bypass" if is_trap else "no_op"
                inst = f"gen_{fam}_knob-{kind}_s{idx}"
                counts = counts_fn(is_trap, idx)
                for _ in range(N_SAMPLES):
                    recs.append(_rec(inst, is_trap=is_trap, counts=counts))
    return recs


# =========================================================================== #
# Family extraction (the grouping key for the two-stage reduction).
# =========================================================================== #
def test_reroute_family_of_handles_multitoken_families():
    assert reroute_family_of("gen_far_as_prepend_d2-bypass_s0") == "far_as_prepend"
    assert reroute_family_of("gen_remove_dead_prepend_knob-no_op_s3") == "remove_dead_prepend"
    assert reroute_family_of("gen_community_lp_lp-bypass_s1") == "community_lp"
    assert reroute_family_of("gen_rr_bestpath_x-bypass_s0") == "rr_bestpath"
    # ipc templated name still resolves to its head family
    assert reroute_family_of("gen_ipc_k2-one-out-plain-implicit_s0") == "ipc"


def test_truth_dims_are_d4_d10():
    assert REROUTE_TRUTH_DIMS == ("waypoint", "intent")


# =========================================================================== #
# The four gaming strategies — MEASURED outcomes.
# =========================================================================== #
def test_always_predict_d4_d10_is_pinned_to_half():
    """The macro_f1_damage gamer: perfect trap recall, but a false alarm on EVERY
    no_op twin -> FAR=1.0 -> NetBrace-Detect=0.5, Youden_J=0.0."""
    recs = _build_records(lambda is_trap, idx: _counts_always_d4_d10(is_trap))
    out = reroute_detection_scores(recs)
    assert out["trap_recall"] == 1.0
    assert out["no_op_far"] == 1.0
    assert out["netbrace_detect"] == 0.5
    assert out["youden_j"] == 0.0
    assert out["n_bypass"] == len(FAMILIES) * INSTANCES_PER_FAMILY
    assert out["n_noop"] == len(FAMILIES) * INSTANCES_PER_FAMILY


def test_always_empty_is_pinned_to_half():
    """The silent gamer: catches no bypass (recall 0) but never false-alarms (FAR 0)
    -> NetBrace-Detect=0.5, Youden_J=0.0. Same 0.5 as the OPPOSITE constant predictor,
    proving the floor is label-independent."""
    recs = _build_records(lambda is_trap, idx: _counts_always_empty(is_trap))
    out = reroute_detection_scores(recs)
    assert out["trap_recall"] == 0.0
    assert out["no_op_far"] == 0.0
    assert out["netbrace_detect"] == 0.5
    assert out["youden_j"] == 0.0


def test_perfect_oracle_scores_one():
    """The oracle: trap_recall=1.0, no_op_FAR=0.0 -> NetBrace-Detect=1.0, Youden_J=1.0."""
    recs = _build_records(lambda is_trap, idx: _counts_perfect(is_trap))
    out = reroute_detection_scores(recs)
    assert out["trap_recall"] == 1.0
    assert out["no_op_far"] == 0.0
    assert out["netbrace_detect"] == 1.0
    assert out["youden_j"] == 1.0


def test_partial_reasoner_is_strictly_between():
    """A realistic reasoner fires on half its instances (catching D4 not D10 on the
    bypass it fires on; false-alarming the no_op it fires on). Both channels land
    strictly inside (0,1), so NetBrace-Detect and Youden_J are strictly between the
    floor (0.5 / 0.0) and the ceiling (1.0 / 1.0)."""
    recs = _build_records(lambda is_trap, idx: _counts_partial(is_trap, fire=(idx == 0)))
    out = reroute_detection_scores(recs)
    # idx0 bypass fires -> recall-where-truth = 0.5; idx1 bypass silent -> 0.0.
    # per-family instance means {0.5, 0.0} -> family 0.25 -> pooled 0.25.
    assert math.isclose(out["trap_recall"], 0.25, abs_tol=1e-9)
    # idx0 no_op false-alarms (1.0); idx1 no_op silent (0.0) -> FAR 0.5.
    assert math.isclose(out["no_op_far"], 0.5, abs_tol=1e-9)
    detect = (0.25 + (1 - 0.5)) / 2
    assert math.isclose(out["netbrace_detect"], detect, abs_tol=1e-9)
    assert math.isclose(out["youden_j"], 0.25 - 0.5, abs_tol=1e-9)
    # strictly between the constant floor and the oracle ceiling
    assert 0.0 < out["trap_recall"] < 1.0
    assert 0.0 < out["no_op_far"] < 1.0
    assert out["netbrace_detect"] != 0.5  # it is genuinely off the constant floor


def test_no_constant_predictor_beats_half():
    """The codified guarantee: BOTH constant predictors (all-fire, all-silent) sit at
    exactly NetBrace-Detect 0.5 / Youden_J 0.0 — neither beats the floor."""
    for counts_fn in (
        lambda is_trap, idx: _counts_always_d4_d10(is_trap),
        lambda is_trap, idx: _counts_always_empty(is_trap),
    ):
        out = reroute_detection_scores(_build_records(counts_fn))
        assert out["netbrace_detect"] == 0.5
        assert out["youden_j"] == 0.0


# =========================================================================== #
# recall-where-truth must NOT be the precision-dragged mean, and must NOT average
# in empty-truth dims (grader_artifact_d7).
# =========================================================================== #
def test_trap_recall_ignores_precision_drag():
    """A model that catches both bypass truths but ALSO floods false positives on D4
    still has trap_recall=1.0 — recall-where-truth reads tp/(tp+fn), never precision."""
    recs: list[dict] = []
    for fam in FAMILIES:
        inst = f"gen_{fam}_knob-bypass_s0"
        for _ in range(N_SAMPLES):
            # both truths caught (recall 1) but 9 spurious D4 FPs (precision 0.1)
            recs.append(_rec(inst, is_trap=True,
                             counts={"waypoint": (1, 9, 0), "intent": (1, 0, 0)}))
    out = reroute_detection_scores(recs)
    assert out["trap_recall"] == 1.0  # precision drag did NOT pull it down


def test_trap_recall_excludes_empty_truth_dims():
    """If a bypass sample has truth on D4 only (D10 truth empty on that sample), the
    empty-truth D10 must be EXCLUDED — not folded in as a vacuous recall 1.0. A model
    that catches D4 scores recall-where-truth = 1.0 over {D4}; one that misses D4 scores
    0.0 — proving D10's empty truth never contributed a free 1.0."""
    miss = _rec("gen_far_as_prepend_knob-bypass_s0", is_trap=True,
                counts={"waypoint": (0, 0, 1)})  # D4 truth present + missed; D10 absent
    catch = _rec("gen_far_as_prepend_knob-bypass_s1", is_trap=True,
                 counts={"waypoint": (1, 0, 0)})  # D4 truth present + caught; D10 absent
    out_miss = reroute_detection_scores([miss] * N_SAMPLES)
    out_catch = reroute_detection_scores([catch] * N_SAMPLES)
    assert out_miss["trap_recall"] == 0.0
    assert out_catch["trap_recall"] == 1.0


# =========================================================================== #
# Per-family diagnostic + instance counting.
# =========================================================================== #
def test_per_family_diagnostic_is_populated():
    out = reroute_detection_scores(_build_records(lambda is_trap, idx: _counts_perfect(is_trap)))
    assert set(out["per_family"]) == set(FAMILIES)
    for fam in FAMILIES:
        entry = out["per_family"][fam]
        assert entry["trap_recall"] == 1.0
        assert entry["no_op_far"] == 0.0
        assert entry["netbrace_detect"] == 1.0
        assert entry["youden_j"] == 1.0
        assert entry["n_bypass"] == INSTANCES_PER_FAMILY
        assert entry["n_noop"] == INSTANCES_PER_FAMILY


# =========================================================================== #
# THE BUG FIX: empty_truth_false_alarm fires on is_trap=False no_op twins (where the
# legacy false_alarm provably cannot), under BOTH the exact and the semantic grader.
# =========================================================================== #
def _bypass_blast(pred: bool) -> ExtendedBlastRadius:
    """A prediction asserting {D4,D10} (pred=True) or empty (pred=False)."""
    if not pred:
        return ExtendedBlastRadius()
    return ExtendedBlastRadius(
        waypoint_violations=[WaypointViolation(
            src_node="r1", dst_prefix="203.0.113.0/24", waypoint="r4")],
        intent_violations=[IntentViolation(
            kind="waypoint", src="r1", dst="203.0.113.0/24")],
    )


def test_exact_grader_empty_truth_false_alarm_fires_on_noop_but_legacy_does_not():
    truth = ExtendedBlastRadius()  # no_op: empty GT
    pred = _bypass_blast(pred=True)  # model wrongly predicts {D4,D10}
    sr = grade_extended(pred, truth, is_trap=False, task_id="noop")
    # the bug: legacy false_alarm gates on is_trap -> stays dead on the no_op twin
    assert sr.false_alarm is False
    # the fix: the is_trap-independent channel fires
    assert sr.empty_truth_false_alarm is True


def test_exact_grader_empty_truth_false_alarm_silent_when_pred_empty():
    truth = ExtendedBlastRadius()
    sr = grade_extended(_bypass_blast(pred=False), truth, is_trap=False, task_id="noop")
    assert sr.empty_truth_false_alarm is False
    assert sr.false_alarm is False


def test_semantic_grader_empty_truth_false_alarm_fires_on_noop():
    truth = empty_keysets()  # no_op
    pred = empty_keysets()
    pred["waypoint"] = {_WP_KEY}
    pred["intent"] = {_INTENT_KEY}
    sr = grade_keysets_semantic(pred, truth, config_prefixes=set(), is_trap=False)
    assert sr.false_alarm is False           # legacy channel still dead on is_trap=False
    assert sr.empty_truth_false_alarm is True  # fixed channel fires


def test_empty_truth_false_alarm_is_additive_default_false():
    """Backward compatibility: a damage (non-empty truth) grade leaves the new field
    False, and old records without the field are still consumable by the metric."""
    truth = _bypass_blast(pred=True)  # non-empty truth
    sr = grade_extended(_bypass_blast(pred=True), truth, is_trap=True, task_id="bypass")
    assert sr.empty_truth_false_alarm is False  # truth not empty -> never fires
    # metric tolerates records lacking the field (falls back to per_type derivation)
    legacy = {"instance": "gen_far_as_prepend_knob-no_op_s0", "is_trap": False,
              "per_type": _per_type({"waypoint": (0, 1, 0)})}  # no empty_truth_false_alarm key
    out = reroute_detection_scores([legacy] * N_SAMPLES)
    assert out["no_op_far"] == 1.0  # derived the FAR from per_type fp footprint


# =========================================================================== #
# FB-2 (freeze blocker, 2026-06-15): the non-gameability guarantee MUST hold on the
# PRODUCTION grader path. The original suite graded only with grade_extended and
# grade_keysets_semantic and NEVER with reporting.baselines.grade_keysets — the grader
# the data-collection sweep actually runs on every model AND baseline. That grade_keysets
# forgot to set empty_truth_false_alarm, which structurally pinned the no_op FAR channel
# to 0 and let the always-{D4,D10} attacker score netbrace_detect=1.0 / youden_j=1.0
# (the killshot). These tests grade the SAME strategies through ALL THREE graders and
# assert the floor, so any grader that forgets to populate the FP signal FAILS CI.
#
# This block MUST FAIL on the pre-fix grade_keysets and PASS on all three after FB-1.
# =========================================================================== #

# Keyset predictions for the {D4,D10} and empty strategies (the grade_keysets /
# grade_keysets_semantic native currency).
def _pred_keysets_d4_d10() -> dict[str, set[str]]:
    p = empty_keysets()
    p["waypoint"] = {_WP_KEY}
    p["intent"] = {_INTENT_KEY}
    return p


def _pred_keysets_empty() -> dict[str, set[str]]:
    return empty_keysets()


# --- per-grader adapters: (twin_is_trap, strategy) -> a flat graded record dict ------- #
# Each adapter grades a REAL prediction against the REAL twin ground truth through one of
# the three production graders, then dumps it to the flat shape the metric consumes. No
# hand-built per_type / empty_truth_false_alarm — the grader populates everything, so a
# grader bug is exercised, not bypassed.
def _grade_via_keysets(is_trap: bool, *, predict_d4_d10: bool) -> dict:
    truth = _bypass_truth() if is_trap else _noop_truth()
    pred = _pred_keysets_d4_d10() if predict_d4_d10 else _pred_keysets_empty()
    return grade_keysets(pred, truth, is_trap=is_trap).model_dump()


def _grade_via_semantic(is_trap: bool, *, predict_d4_d10: bool) -> dict:
    truth = _bypass_truth() if is_trap else _noop_truth()
    pred = _pred_keysets_d4_d10() if predict_d4_d10 else _pred_keysets_empty()
    return grade_keysets_semantic(
        pred, truth, config_prefixes=set(), is_trap=is_trap
    ).model_dump()


def _grade_via_extended(is_trap: bool, *, predict_d4_d10: bool) -> dict:
    # grade_extended consumes ExtendedBlastRadius objects, not keysets.
    truth = _bypass_blast(pred=True) if is_trap else ExtendedBlastRadius()
    pred = _bypass_blast(pred=predict_d4_d10)
    return grade_extended(pred, truth, is_trap=is_trap).model_dump()


_GRADERS = {
    "grade_keysets": _grade_via_keysets,            # THE PRODUCTION SWEEP GRADER
    "grade_extended": _grade_via_extended,
    "grade_keysets_semantic": _grade_via_semantic,
}


def _build_records_via_grader(grade_fn, *, predict_d4_d10: bool) -> list[dict]:
    """A balanced bypass/no_op record set built by grading REAL predictions through a real
    grader (one of the three production graders). ``predict_d4_d10`` toggles the constant
    strategy: True = always-{D4,D10}, False = always-empty. Mirrors the synthetic builder's
    shape (FAMILIES x INSTANCES_PER_FAMILY x {bypass,no_op} x N_SAMPLES) so the two-stage
    reduction is exercised identically."""
    recs: list[dict] = []
    for fam in FAMILIES:
        for idx in range(INSTANCES_PER_FAMILY):
            for is_trap in (True, False):
                kind = "bypass" if is_trap else "no_op"
                inst = f"gen_{fam}_knob-{kind}_s{idx}"
                for _ in range(N_SAMPLES):
                    rec = grade_fn(is_trap, predict_d4_d10=predict_d4_d10)
                    rec["instance"] = inst
                    recs.append(rec)
    return recs


def _build_oracle_via_grader(grade_fn) -> list[dict]:
    """The oracle through a real grader: predict {D4,D10} on bypass, predict empty on
    no_op. Must score netbrace_detect=1.0 / youden_j=1.0 on every grader."""
    recs: list[dict] = []
    for fam in FAMILIES:
        for idx in range(INSTANCES_PER_FAMILY):
            for is_trap in (True, False):
                kind = "bypass" if is_trap else "no_op"
                inst = f"gen_{fam}_knob-{kind}_s{idx}"
                for _ in range(N_SAMPLES):
                    rec = grade_fn(is_trap, predict_d4_d10=is_trap)  # mimic GT
                    rec["instance"] = inst
                    recs.append(rec)
    return recs


@pytest.mark.parametrize("grader_name", list(_GRADERS))
def test_grader_populates_empty_truth_false_alarm_on_noop(grader_name):
    """DIRECT grader-field gate (the assertion that fails on the pre-fix grade_keysets):
    every production grader MUST set ``empty_truth_false_alarm=True`` on an is_trap=False
    no_op twin whose truth is empty and whose prediction is non-empty ({D4,D10}). FB-1 was
    grade_keysets emitting the schema-default False here, killing the no_op FAR channel.

    The metric was ALSO hardened to re-derive FAR from per_type (FB-1 part 2), so a
    forgetful grader no longer breaks the headline — but the FIELD is still part of the
    grader contract (it is the authoritative, is_trap-independent calibration-twin FP
    signal other code may read), so a grader that forgets it must FAIL CI HERE. This
    assertion is the one that is RED on the pre-fix grade_keysets and GREEN after FB-1, on
    all three graders."""
    grade_fn = _GRADERS[grader_name]
    rec = grade_fn(False, predict_d4_d10=True)  # no_op twin, model predicts {D4,D10}
    assert rec["empty_truth_false_alarm"] is True, (grader_name, rec)
    # and when the no_op prediction is empty, the field must be False (no false alarm)
    rec_silent = grade_fn(False, predict_d4_d10=False)
    assert rec_silent["empty_truth_false_alarm"] is False, (grader_name, rec_silent)
    # legacy is_trap-gated false_alarm stays dead on the no_op twin (proves the new
    # channel is what restores the signal, not the old one)
    assert rec["false_alarm"] is False, (grader_name, rec)


@pytest.mark.parametrize("grader_name", list(_GRADERS))
def test_always_d4_d10_pinned_to_half_through_production_graders(grader_name):
    """KILLSHOT GATE: the always-{D4,D10} attacker graded through EACH production grader
    must land at netbrace_detect=0.50 / youden_j=0.0 / no_op_far=1.0. FB-1 is precisely
    that grade_keysets used to score this 1.0/1.0/0.0 — this assertion FAILS on the
    pre-fix grade_keysets and PASSES after the fix, on all three graders."""
    grade_fn = _GRADERS[grader_name]
    out = reroute_detection_scores(
        _build_records_via_grader(grade_fn, predict_d4_d10=True)
    )
    assert out["trap_recall"] == 1.0, (grader_name, out)
    assert out["no_op_far"] == 1.0, (grader_name, out)
    assert out["netbrace_detect"] == 0.5, (grader_name, out)
    assert out["youden_j"] == 0.0, (grader_name, out)


@pytest.mark.parametrize("grader_name", list(_GRADERS))
def test_always_empty_pinned_to_half_through_production_graders(grader_name):
    """The opposite constant predictor (always-empty) graded through each production grader
    must ALSO sit at 0.50 / 0.0 — proving the floor is label-independent on the real path."""
    grade_fn = _GRADERS[grader_name]
    out = reroute_detection_scores(
        _build_records_via_grader(grade_fn, predict_d4_d10=False)
    )
    assert out["trap_recall"] == 0.0, (grader_name, out)
    assert out["no_op_far"] == 0.0, (grader_name, out)
    assert out["netbrace_detect"] == 0.5, (grader_name, out)
    assert out["youden_j"] == 0.0, (grader_name, out)


@pytest.mark.parametrize("grader_name", list(_GRADERS))
def test_oracle_scores_one_through_production_graders(grader_name):
    """The oracle graded through each production grader scores netbrace_detect=1.0 /
    youden_j=1.0 — the ceiling is preserved by the FB-1 fix on every grader."""
    grade_fn = _GRADERS[grader_name]
    out = reroute_detection_scores(_build_oracle_via_grader(grade_fn))
    assert out["trap_recall"] == 1.0, (grader_name, out)
    assert out["no_op_far"] == 0.0, (grader_name, out)
    assert out["netbrace_detect"] == 1.0, (grader_name, out)
    assert out["youden_j"] == 1.0, (grader_name, out)


# =========================================================================== #
# M-C (major): honest confidence intervals — never a zero-width bracket while any
# within-family scatter exists; n_families AND n_instances surfaced per cell.
# =========================================================================== #
def test_ci_never_zero_width_when_instances_scatter():
    """A cell whose FAMILY means coincide but whose INSTANCES scatter must NOT report a
    zero-width CI (the dishonest [m,m] bracket M-C flags). The cluster bootstrap + the
    instance-level t-floor must supply honest width."""
    # build a partial reasoner whose per-family means coincide but instances scatter:
    # within each family, instance 0 fires (recall-where-truth 0.5), instance 1 silent (0.0)
    # -> every family mean = 0.25, but the underlying instance means {0.5, 0.0} scatter.
    recs = _build_records(lambda is_trap, idx: _counts_partial(is_trap, fire=(idx == 0)))
    out = reroute_detection_scores(recs)
    det = out["detail"]["trap_recall"]
    assert det["ci_hi"] > det["ci_lo"], det  # NOT zero-width
    assert det["n_families"] == len(FAMILIES)
    assert det["n_instances"] == len(FAMILIES) * INSTANCES_PER_FAMILY
    # FAR cell likewise exposes both granularities
    far = out["detail"]["no_op_far"]
    assert "n_instances" in far and "n_families" in far


def test_ci_honest_zero_only_when_truly_identical():
    """When every instance value is genuinely identical (the oracle: every bypass instance
    recall=1.0), a zero-width CI is the ONLY honest answer — the floor must not fabricate
    spurious width out of perfectly determinate data."""
    out = reroute_detection_scores(_build_records(lambda is_trap, idx: _counts_perfect(is_trap)))
    det = out["detail"]["trap_recall"]
    assert det["ci_lo"] == det["ci_hi"] == 1.0  # honest zero width
    assert det["n_instances"] == len(FAMILIES) * INSTANCES_PER_FAMILY
