"""Unit tests for the semantic grader (graders/semantic_sets.py).

Frozen behavior under docs/semantic_grading_spec_v1.md §2. These tests pin every
property the spec promises: containment credit band, over-broad rejection, the
forwarding kind class, exact fixed-field matching, bipartite 1:1 FP/FN accounting,
determinism, config-/32 exactness, and D2/D9 identity-with-the-old-grader.
"""

from __future__ import annotations

from netbrace.graders.semantic_sets import (
    canonical_prefix,
    config_visible_prefixes,
    grade_keysets_semantic,
    parse_key,
    score_sets_semantic,
)
from netbrace.graders.sets import score_sets

# A typical leak_ms instance: /24 is config-visible AND the /25 half is too (watched
# line lists both). The probe is a hidden /32 inside the /25.
CFG_LEAK = {"192.0.2.0/24", "192.0.2.0/25", "203.0.114.0/24"}
# A clos_summary-style instance: only the /24 is config-visible (no /25).
CFG_CLOS = {"10.3.0.0/24", "10.0.0.0/8", "0.0.0.0/0"}
# An ecmp/waypoint-style instance: a config-visible /32 loopback, no broader cover.
CFG_LOOPBACK = {"10.0.0.4/32", "10.0.0.0/24"}


# --------------------------------------------------------------------------- #
# config_visible_prefixes + canonical_prefix
# --------------------------------------------------------------------------- #
def test_config_visible_extracts_all_cidrs():
    text = "ip address 192.0.2.0/24\n some 203.0.114.0/24 and a /25: 192.0.2.0/25"
    assert config_visible_prefixes(text) == CFG_LEAK


def test_canonical_picks_most_specific_cover():
    # probe /32 inside both /25 and /24 -> canonical is the /25 (most specific).
    assert canonical_prefix("192.0.2.1/32", CFG_LEAK) == "192.0.2.0/25"


def test_canonical_when_only_24_visible():
    assert canonical_prefix("10.3.0.1/32", CFG_CLOS) == "10.3.0.0/24"


def test_canonical_config_visible_32_maps_to_itself():
    # a config-visible /32 loopback has no broader config cover -> canon == itself.
    assert canonical_prefix("10.0.0.4/32", CFG_LOOPBACK) == "10.0.0.4/32"


def test_canonical_falls_back_to_probe_when_uncovered():
    assert canonical_prefix("8.8.8.8/32", set()) == "8.8.8.8/32"


# --------------------------------------------------------------------------- #
# CIDR credit band (the core relaxation) — forwarding D7
# --------------------------------------------------------------------------- #
def _fwd(node, kind, dst):
    return f"anomaly|{kind}|node={node}|vrf=default|dst={dst}"


def test_forwarding_canonical_cover_matches():
    # predict the canonical /25 cover -> full credit (the clos_summary frontier case
    # analogue: node+kind correct, prefix == most-specific cover).
    pred = {_fwd("site3", "blackhole", "192.0.2.0/25")}
    truth = {_fwd("site3", "null_routed", "192.0.2.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_LEAK)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)
    assert s.f1 == 1.0


def test_forwarding_exact_probe_matches():
    # predict the exact hidden /32 -> also full credit (floor of the credit band).
    pred = {_fwd("site3", "null_routed", "192.0.2.1/32")}
    truth = {_fwd("site3", "null_routed", "192.0.2.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_LEAK)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_forwarding_intermediate_prefix_in_band_matches():
    # a /28 that covers the probe and is no broader than the /25 canonical -> credit.
    pred = {_fwd("site3", "blackhole", "192.0.2.0/28")}
    truth = {_fwd("site3", "null_routed", "192.0.2.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_LEAK)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_forwarding_overbroad_24_when_canonical_is_25_rejected():
    # predicting the /24 when the canonical cover is the /25 -> over-broad -> NO credit.
    pred = {_fwd("site3", "blackhole", "192.0.2.0/24")}
    truth = {_fwd("site3", "null_routed", "192.0.2.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_LEAK)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)
    assert s.f1 == 0.0


def test_forwarding_default_route_earns_nothing():
    # the canonical gaming move: 0.0.0.0/0 -> always over-broad -> zero.
    pred = {_fwd("spine2", "blackhole", "0.0.0.0/0")}
    truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_CLOS)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_forwarding_slash8_overbroad_rejected():
    # haiku's real clos_summary move: blackhole|spine2|10.0.0.0/8 -> over-broad.
    pred = {_fwd("spine2", "blackhole", "10.0.0.0/8")}
    truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_CLOS)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


# --------------------------------------------------------------------------- #
# Kind equivalence class {blackhole, null_routed} == drop ; loop distinct
# --------------------------------------------------------------------------- #
def test_blackhole_null_routed_are_equivalent():
    for k in ("blackhole", "null_routed"):
        pred = {_fwd("spine2", k, "10.3.0.0/24")}
        truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
        s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_CLOS)
        assert s.tp == 1, k


def test_loop_is_distinct_from_drop():
    pred = {_fwd("spine2", "loop", "10.3.0.0/24")}
    truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_CLOS)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


# --------------------------------------------------------------------------- #
# Fixed-field strictness: wrong node/src/via still fails
# --------------------------------------------------------------------------- #
def test_wrong_node_still_fp_fn():
    pred = {_fwd("leaf1", "blackhole", "10.3.0.0/24")}
    truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_CLOS)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_waypoint_wrong_via_fails():
    pred = {"waypoint|src=pe1|dst=100.64.235.0/24|via=WRONG|vrf=default"}
    truth = {"waypoint|src=pe1|dst=100.64.235.1/32|via=pe2|vrf=default"}
    cfg = {"100.64.235.0/24"}
    s = score_sets_semantic(pred, truth, dim="waypoint", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_waypoint_correct_via_and_cover_matches():
    pred = {"waypoint|src=pe1|dst=100.64.235.0/24|via=pe2|vrf=default"}
    truth = {"waypoint|src=pe1|dst=100.64.235.1/32|via=pe2|vrf=default"}
    cfg = {"100.64.235.0/24"}
    s = score_sets_semantic(pred, truth, dim="waypoint", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


# --------------------------------------------------------------------------- #
# D2/D9 identity with the old grader (canonical == probe -> exact)
# --------------------------------------------------------------------------- #
def test_prefixes_dim_is_exact_like_old_grader():
    pred = {"route|node=edge|vrf=default|prefix=172.25.0.0/16"}
    truth = {"route|node=edge|vrf=default|prefix=172.25.0.0/16"}
    cfg = {"172.25.0.0/16"}
    s_new = score_sets_semantic(pred, truth, dim="prefixes", config_prefixes=cfg)
    s_old = score_sets(pred, truth)
    assert (s_new.tp, s_new.fp, s_new.fn) == (s_old.tp, s_old.fp, s_old.fn) == (1, 0, 0)


def test_prefixes_overbroad_not_credited():
    # even on D2, predicting a /8 where truth is a config-visible /16 -> over-broad,
    # because canon(/16)==/16 and /8 is broader -> no credit (still exact-like).
    pred = {"route|node=edge|vrf=default|prefix=172.0.0.0/8"}
    truth = {"route|node=edge|vrf=default|prefix=172.25.0.0/16"}
    cfg = {"172.25.0.0/16"}
    s = score_sets_semantic(pred, truth, dim="prefixes", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_prefixes_wrong_node_fails_like_old():
    pred = {"route|node=other|vrf=default|prefix=172.25.0.0/16"}
    truth = {"route|node=edge|vrf=default|prefix=172.25.0.0/16"}
    cfg = {"172.25.0.0/16"}
    s = score_sets_semantic(pred, truth, dim="prefixes", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_bgp_withdrawn_exact():
    pred = {"bgp_withdrawn|node=r2|vrf=default|network=203.0.113.0/24"}
    truth = {"bgp_withdrawn|node=r2|vrf=default|network=203.0.113.0/24"}
    cfg = {"203.0.113.0/24"}
    s = score_sets_semantic(pred, truth, dim="bgp_withdrawn", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


# --------------------------------------------------------------------------- #
# Config-visible /32 loopback (redundancy D5, waypoint4) — exact, no containment
# --------------------------------------------------------------------------- #
def test_redundancy_config_32_loopback_exact():
    pred = {"redundancy|node=src|vrf=default|prefix=10.0.0.4/32"}
    truth = {"redundancy|node=src|vrf=default|prefix=10.0.0.4/32"}
    s = score_sets_semantic(pred, truth, dim="redundancy", config_prefixes=CFG_LOOPBACK)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_redundancy_24_not_credited_for_32_loopback():
    # predicting the /24 for a config-visible /32 loopback truth -> over-broad (canon
    # is the /32 itself) -> no credit. config-/32 must NOT get containment credit.
    pred = {"redundancy|node=src|vrf=default|prefix=10.0.0.0/24"}
    truth = {"redundancy|node=src|vrf=default|prefix=10.0.0.4/32"}
    s = score_sets_semantic(pred, truth, dim="redundancy", config_prefixes=CFG_LOOPBACK)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


# --------------------------------------------------------------------------- #
# Sessions / scale: no CIDR slot -> delegate to exact-string score_sets
# --------------------------------------------------------------------------- #
def test_sessions_identical_to_exact():
    pred = {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}
    truth = {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}
    s = score_sets_semantic(pred, truth, dim="sessions", config_prefixes=set())
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_sessions_mismatch_is_fp_fn():
    pred = {"bgp|vrf=default|node=r1|peer_ip=10.0.0.9"}
    truth = {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}
    s = score_sets_semantic(pred, truth, dim="sessions", config_prefixes=set())
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_scale_exact_string():
    pred = {"scale|node=edge|resource=fib"}
    truth = {"scale|node=edge|resource=fib"}
    s = score_sets_semantic(pred, truth, dim="scale", config_prefixes=set())
    assert s.tp == 1


# --------------------------------------------------------------------------- #
# Bipartite one-to-one: one broad prediction cannot cover two truths
# --------------------------------------------------------------------------- #
def test_one_pred_cannot_cover_two_truths():
    # two distinct /25 half truths; one /24 prediction. /24 is over-broad vs each /25
    # canonical -> matches NEITHER (and even if it weren't, 1:1 caps it at one).
    truth = {
        _fwd("isp3", "null_routed", "192.0.2.1/32"),
        _fwd("isp3", "null_routed", "192.0.2.129/32"),
    }
    cfg = {"192.0.2.0/24", "192.0.2.0/25", "192.0.2.128/25"}
    pred = {_fwd("isp3", "blackhole", "192.0.2.0/24")}
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=cfg)
    assert s.tp == 0  # over-broad vs both /25 canonicals
    assert (s.fp, s.fn) == (1, 2)


def test_two_correct_halves_both_credited():
    truth = {
        _fwd("isp3", "null_routed", "192.0.2.1/32"),
        _fwd("isp3", "null_routed", "192.0.2.129/32"),
    }
    cfg = {"192.0.2.0/24", "192.0.2.0/25", "192.0.2.128/25"}
    pred = {
        _fwd("isp3", "blackhole", "192.0.2.0/25"),
        _fwd("isp3", "blackhole", "192.0.2.128/25"),
    }
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (2, 0, 0)


def test_bipartite_one_to_one_no_double_count():
    # two identical-cover predictions, one truth -> at most one TP, one FP.
    truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    pred = {
        _fwd("spine2", "blackhole", "10.3.0.0/24"),
        _fwd("spine2", "null_routed", "10.3.0.0/24"),
    }
    s = score_sets_semantic(pred, truth, dim="forwarding", config_prefixes=CFG_CLOS)
    assert (s.tp, s.fp, s.fn) == (1, 1, 0)


# --------------------------------------------------------------------------- #
# Determinism: order-independence of inputs
# --------------------------------------------------------------------------- #
def test_determinism_order_independent():
    cfg = {"192.0.2.0/24", "192.0.2.0/25", "192.0.2.128/25"}
    truth = [
        _fwd("isp3", "null_routed", "192.0.2.1/32"),
        _fwd("isp3", "null_routed", "192.0.2.129/32"),
    ]
    pred = [
        _fwd("isp3", "blackhole", "192.0.2.0/25"),
        _fwd("isp3", "blackhole", "192.0.2.128/25"),
    ]
    import itertools
    results = set()
    for tp_ in itertools.permutations(truth):
        for pp in itertools.permutations(pred):
            s = score_sets_semantic(set(pp), set(tp_), dim="forwarding",
                                    config_prefixes=cfg)
            results.add((s.tp, s.fp, s.fn))
    assert results == {(2, 0, 0)}


# --------------------------------------------------------------------------- #
# Vacuous-truth convention preserved (empty pred -> P=1; empty truth -> R=1)
# --------------------------------------------------------------------------- #
def test_empty_prediction_precision_one():
    truth = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    s = score_sets_semantic(set(), truth, dim="forwarding", config_prefixes=CFG_CLOS)
    assert s.precision == 1.0 and s.recall == 0.0 and s.f1 == 0.0


def test_empty_truth_recall_one():
    pred = {_fwd("spine2", "null_routed", "10.3.0.0/24")}
    s = score_sets_semantic(pred, set(), dim="forwarding", config_prefixes=CFG_CLOS)
    assert s.recall == 1.0 and s.precision == 0.0 and s.f1 == 0.0


def test_both_empty_all_one():
    s = score_sets_semantic(set(), set(), dim="forwarding", config_prefixes=set())
    assert s.precision == s.recall == s.f1 == 1.0


# --------------------------------------------------------------------------- #
# Intent grammar: te_pin /25 (config-visible -> exact) vs waypoint-kind /32 (probe)
# --------------------------------------------------------------------------- #
def test_intent_te_pin_exact():
    pred = {"intent|kind=te_pin|src=r2|dst=192.0.2.0/25"}
    truth = {"intent|kind=te_pin|src=r2|dst=192.0.2.0/25"}
    cfg = {"192.0.2.0/24", "192.0.2.0/25"}
    s = score_sets_semantic(pred, truth, dim="intent", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_intent_waypoint_kind_probe_covered():
    pred = {"intent|kind=waypoint|src=net2|dst=203.0.113.0/25"}
    truth = {"intent|kind=waypoint|src=net2|dst=203.0.113.1/32"}
    cfg = {"203.0.113.0/24", "203.0.113.0/25"}
    s = score_sets_semantic(pred, truth, dim="intent", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_intent_wrong_kind_fails():
    pred = {"intent|kind=te_pin|src=net2|dst=203.0.113.0/25"}
    truth = {"intent|kind=waypoint|src=net2|dst=203.0.113.1/32"}
    cfg = {"203.0.113.0/24", "203.0.113.0/25"}
    s = score_sets_semantic(pred, truth, dim="intent", config_prefixes=cfg)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


# --------------------------------------------------------------------------- #
# grade_keysets_semantic: full record, FSA unchanged, status ladder
# --------------------------------------------------------------------------- #
def _empty():
    from netbrace.core.dimensions import EXT_ELEMENT_TYPES
    return {t: set() for t in EXT_ELEMENT_TYPES}


def test_grade_keysets_semantic_forwarding_pass():
    truth = _empty()
    truth["forwarding"] = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    truth["prefixes"] = {"route|node=spine2|vrf=default|prefix=10.3.0.0/24"}
    pred = _empty()
    pred["forwarding"] = {_fwd("spine2", "blackhole", "10.3.0.0/24")}
    pred["prefixes"] = {"route|node=spine2|vrf=default|prefix=10.3.0.0/24"}
    rec = grade_keysets_semantic(pred, truth, config_prefixes=CFG_CLOS, is_trap=True)
    assert rec.per_type["forwarding"].f1 == 1.0
    assert rec.macro_f1 == 1.0
    assert rec.exact_match is True
    assert rec.status == "pass"


def test_grade_keysets_semantic_fsa_unchanged():
    # hallucinated session loss with empty truth sessions -> FSA fires (CIDR-free dim).
    truth = _empty()
    truth["forwarding"] = {_fwd("spine2", "null_routed", "10.3.0.1/32")}
    pred = _empty()
    pred["sessions"] = {"bgp|vrf=default|node=spine2|peer_ip=0.0.0.0"}
    rec = grade_keysets_semantic(pred, truth, config_prefixes=CFG_CLOS, is_trap=True)
    assert rec.false_session_alarm is True
