"""Tests for D10 ``IntentViolation`` — the policy-intent dimension that catches a
change where reachability SURVIVES (D3 = ∅) yet a declared policy intent is broken.

No live Batfish needed here:
  * the typed element key / round-trip through the fake model + parser are pure;
  * the oracle ``_intent_diff`` per-kind PRE/POST logic is exercised via stubs that
    inject canned flow outcomes / route presence / next-hop counts, so the
    held-pre-and-violated-post arithmetic is tested deterministically without a
    Batfish dependency;
  * the live ground truth for ipc_aggregate (D3 reachability_lost = ∅ AND
    intent = {te_pin on each /25}) is verified by
    scripts/run_extended_scenario.py --scenario ipc_aggregate (the sanity gate).
"""

from __future__ import annotations

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import (
    EXT_ELEMENT_TYPES,
    ExtendedBlastRadius,
    IntentViolation,
)
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import SCORED_TYPES, grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel
from netbrace.tasks.safety import baseline_ipc_aggregate as agg
from netbrace.tasks.safety import scenarios
from netbrace.tasks.safety.scenarios import IntentInvariant


# --------------------------------------------------------------------------- #
# The typed element — key carries identity only (no note, no payload)
# --------------------------------------------------------------------------- #
def test_intent_violation_key_canonicalizes_and_omits_note():
    a = IntentViolation(kind="te_pin", src="R2", dst="203.0.113.0/25")
    b = IntentViolation(kind="te_pin", src="r2", dst="203.0.113.0/25")
    assert a.key == b.key
    assert a.key == "intent|kind=te_pin|src=r2|dst=203.0.113.0/25"


def test_intent_violation_null_src_uses_wildcard():
    iv = IntentViolation(kind="reachability", dst="203.0.113.0/24")
    assert iv.key == "intent|kind=reachability|src=*|dst=203.0.113.0/24"


def test_intent_is_a_graded_type():
    assert EXT_ELEMENT_TYPES[-1] == "intent"
    assert "intent" in SCORED_TYPES
    ks = ExtendedBlastRadius(
        intent_violations=[IntentViolation(kind="te_pin", src="r2", dst="203.0.113.0/25")]
    ).key_sets()
    assert ks["intent"] == {"intent|kind=te_pin|src=r2|dst=203.0.113.0/25"}
    assert not ExtendedBlastRadius(
        intent_violations=[IntentViolation(kind="te_pin", src="r2", dst="203.0.113.0/25")]
    ).is_empty()


# --------------------------------------------------------------------------- #
# Parser + fake-model round trip (so the full pipeline scores D10 -> macro_f1=1.0)
# --------------------------------------------------------------------------- #
def test_d10_round_trips_through_fake_model_and_parser():
    truth = ExtendedBlastRadius(
        intent_violations=[
            IntentViolation(kind="te_pin", src="r2", dst="203.0.113.0/25"),
            IntentViolation(kind="te_pin", src="r2", dst="203.0.113.128/25"),
        ]
    )
    raw = ExtendedFakeModel("oracle").respond(truth)
    pred = parse_extended_prediction(raw)
    sr = grade_extended(pred, truth, task_id="t")
    assert sr.exact_match is True
    assert sr.per_type["intent"].f1 == 1.0
    assert "intent" in sr.active_types


def test_parser_drops_bad_kind_keeps_good():
    raw = (
        '```json\n{"intent_violations": ['
        '{"kind": "te_pin", "src": "r2", "dst": "203.0.113.0/25"},'
        '{"kind": "NOT_A_KIND", "src": "r2", "dst": "1.2.3.0/24"}'
        ']}\n```'
    )
    pred = parse_extended_prediction(raw)
    assert [e.key for e in pred.intent_violations] == [
        "intent|kind=te_pin|src=r2|dst=203.0.113.0/25"
    ]


# --------------------------------------------------------------------------- #
# Oracle per-kind PRE/POST logic (stubbed — no Batfish)
# --------------------------------------------------------------------------- #
def _bare_oracle() -> ExtendedOracle:
    return ExtendedOracle.__new__(ExtendedOracle)  # bypass __init__ (no pybatfish)


def test_te_pin_fires_when_specific_present_pre_absent_post():
    o = _bare_oracle()
    # /25 present pre (count>=1), gone post (count==0); the /24 aggregate (a DIFFERENT
    # exact prefix) does not satisfy the /25 exact lookup.
    o._nexthop_count = lambda snap, node, prefix: 1 if snap == "pre" else 0  # type: ignore
    out = o._intent_diff([IntentInvariant(kind="te_pin", src="r2", dst="203.0.113.0/25")])
    assert [e.key for e in out] == ["intent|kind=te_pin|src=r2|dst=203.0.113.0/25"]


def test_te_pin_silent_when_specific_survives():
    o = _bare_oracle()
    o._nexthop_count = lambda snap, node, prefix: 1  # present pre AND post  # type: ignore
    assert o._intent_diff([IntentInvariant(kind="te_pin", src="r2", dst="203.0.113.0/25")]) == []


def test_reachability_intent_fires_only_on_pre_ok_post_lost():
    o = _bare_oracle()
    o._flow_outcome = lambda snap, src, dst: (snap == "pre", None)  # type: ignore
    out = o._intent_diff([IntentInvariant(kind="reachability", src="r2", dst="203.0.113.0/24")])
    assert [e.key for e in out] == ["intent|kind=reachability|src=r2|dst=203.0.113.0/24"]
    # if it never delivered pre, no violation (it didn't HOLD pre)
    o._flow_outcome = lambda snap, src, dst: (False, None)  # type: ignore
    assert o._intent_diff([IntentInvariant(kind="reachability", src="r2", dst="203.0.113.0/24")]) == []


def test_isolation_intent_fires_when_leak_appears_post():
    o = _bare_oracle()
    # isolated pre (not delivered), leaks post (delivered) -> violation.
    o._flow_outcome = lambda snap, src, dst: (snap == "post", None)  # type: ignore
    out = o._intent_diff([
        IntentInvariant(kind="isolation", src="r2", dst="10.9.9.9/32", forbidden_peer="10.9.9.9")
    ])
    assert [e.kind for e in out] == ["isolation"]
    # already reachable pre -> isolation did not hold pre -> no violation
    o._flow_outcome = lambda snap, src, dst: (True, None)  # type: ignore
    assert o._intent_diff([
        IntentInvariant(kind="isolation", src="r2", dst="10.9.9.9/32")
    ]) == []


def test_redundancy_floor_fires_when_paths_drop_below_floor():
    o = _bare_oracle()
    o._nexthop_count = lambda snap, node, prefix: 2 if snap == "pre" else 1  # type: ignore
    out = o._intent_diff([
        IntentInvariant(kind="redundancy_floor", src="leaf1", dst="10.1.0.0/24", floor=2)
    ])
    assert [e.kind for e in out] == ["redundancy_floor"]
    # still at/above floor post -> no violation
    o._nexthop_count = lambda snap, node, prefix: 2  # type: ignore
    assert o._intent_diff([
        IntentInvariant(kind="redundancy_floor", src="leaf1", dst="10.1.0.0/24", floor=2)
    ]) == []


def test_intent_diff_empty_is_noop():
    assert _bare_oracle()._intent_diff([]) == []
    assert _bare_oracle()._intent_diff(None) == []


# --------------------------------------------------------------------------- #
# The canonical ipc_aggregate ground truth: reachable but intent broken
# --------------------------------------------------------------------------- #
def test_ipc_aggregate_declares_te_pin_invariants_on_both_specifics():
    scn = scenarios.build("ipc_aggregate")
    kinds = {(iv.kind, iv.src, iv.dst) for iv in scn.intent_invariants}
    assert kinds == {
        ("te_pin", "r2", agg.SPECIFIC_LOW),
        ("te_pin", "r2", agg.SPECIFIC_HIGH),
    }


def test_ipc_aggregate_intent_gt_with_stubbed_oracle():
    """The verified canonical GT shape: D3 reachability_lost = ∅ (the /24 covers
    the destination) BUT intent fires on each withdrawn /25 — computed here with a
    stub matching the live-verified facts (no Batfish), so the SHAPE is unit-pinned.
    """
    scn = scenarios.build("ipc_aggregate")
    o = _bare_oracle()
    # Live facts: at r2 each /25 exact route is present pre, gone post; the /24
    # delivers traffic in BOTH pre and post (reachability never lost).
    o._nexthop_count = lambda snap, node, prefix: 1 if snap == "pre" else 0  # type: ignore
    o._flow_outcome = lambda snap, src, dst: (True, None)  # type: ignore

    intents = o._intent_diff(scn.intent_invariants)
    assert sorted(e.key for e in intents) == [
        "intent|kind=te_pin|src=r2|dst=203.0.113.0/25",
        "intent|kind=te_pin|src=r2|dst=203.0.113.128/25",
    ]
    # D3 invariant of the canonical case: reachability is NOT lost (the /24 covers).
    # (mirrors the scenario's existing reachability_flows verdict, here trivially via
    # the delivered stub.)


# --------------------------------------------------------------------------- #
# Opt-in no-op: every OTHER scenario carries no intent invariants
# --------------------------------------------------------------------------- #
def test_intent_is_opt_in_and_only_declared_where_designed():
    # D10 is opt-in: only the scenarios whose graded thesis is an intent/severity
    # surface declare invariants (ipc_aggregate -> te_pin; mgmt_lockout ->
    # management-reachability). Every other scenario must leave it empty.
    declares = {"ipc_aggregate", "mgmt_lockout"}
    for name in scenarios.REGISTRY:
        scn = scenarios.build(name)
        if name in declares:
            assert scn.intent_invariants, f"{name} must declare intent invariants"
        else:
            assert scn.intent_invariants == [], f"{name}: intent must be opt-in (empty)"


def test_mgmt_lockout_declares_two_management_reachability_intents():
    from netbrace.tasks.safety import baseline_mgmt_lockout as mgmt

    scn = scenarios.build("mgmt_lockout")
    got = {(iv.kind, iv.src, iv.dst) for iv in scn.intent_invariants}
    assert got == {
        ("reachability", "jump", mgmt.MGMT_PREFIXES["edge"]),
        ("reachability", "jump", mgmt.MGMT_PREFIXES["edge2"]),
    }
    # the structured invariants (notes + the kind token) must NOT leak into prose.
    prose = f"{scn.description}\n{scn.intents_text}".lower()
    for iv in scn.intent_invariants:
        assert iv.note
        assert iv.note.lower() not in prose


# --------------------------------------------------------------------------- #
# Prompt hygiene: structured invariants (esp. note) must NOT reach the model
# --------------------------------------------------------------------------- #
def test_intent_invariants_do_not_leak_into_model_prose():
    scn = scenarios.build("ipc_aggregate")
    prose = f"{scn.description}\n{scn.intents_text}".lower()
    for iv in scn.intent_invariants:
        assert iv.note  # the note exists oracle-side
        assert iv.note.lower() not in prose  # but never appears in model-visible prose
        # the structured kind token must not be solicited verbatim in the prose either
        assert "te_pin" not in prose
