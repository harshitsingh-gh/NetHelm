"""Structural tests for clos_summary (RFC 7938 §5.2.3 summarization blackhole).

No Batfish: these check registration, the multi-spine patch round-trips, the
summary + discard + suppress-specific edits land on BOTH spines, the leaves are
untouched, and the probes are well-formed (host /32, leaf3 neg control). The live
ground truth (D1=∅, D2 specific lost, D7 null_routed@spine2, determinism) is
verified by scripts/run_extended_scenario.py against Batfish.
"""
from __future__ import annotations

from netbrace.tasks.safety import baseline_clos_summary as base
from netbrace.tasks.safety import scenarios
from netbrace.topology.patches import apply_unified_diff


def test_registered():
    assert "clos_summary" in scenarios.REGISTRY


def test_builds_clos_with_per_device_asn():
    scn = scenarios.build("clos_summary")
    assert set(scn.nodes) == {"spine1", "spine2", "leaf1", "leaf2", "leaf3"}
    # per-device ASN (the RFC 7938 §5.2.1 scheme): all five distinct
    assert len(set(base.ASN.values())) == 5
    assert sorted(base.ASN.values()) == [65001, 65002, 65101, 65102, 65103]


def test_fixed_asymmetry_no_spine2_leaf3_link():
    # the deliberate, FIXED asymmetry: spine2 has no link to leaf3 in the baseline
    # (so spine2 has no direct path to the server prefix). Held in both snapshots.
    pairs = {(a, b) for (a, _ai, b, _bi) in base.LINKS}
    assert ("spine2", "leaf3") not in pairs and ("leaf3", "spine2") not in pairs
    assert ("spine1", "leaf3") in pairs  # spine1 DOES reach leaf3


def test_loopbacks_outside_summary():
    # router-ids live in 172.16/16, OUTSIDE the 10/8 summary, so the post summary
    # can never cover a loopback (keeps the D2 watch set unambiguous).
    for ip in base.LOOPBACK_IP.values():
        assert ip.startswith("172.16.")
    assert base.SERVER_PREFIX == "10.3.0.0/24"
    assert base.SUMMARY_PREFIX == "10.0.0.0/8"


def test_change_touches_both_spines_only():
    scn = scenarios.build("clos_summary")
    pre, post = scn.pre_configs, scn.post_configs()
    changed = sorted(n for n in scn.nodes if post[n] != pre[n])
    assert changed == ["spine1", "spine2"]  # fabric-wide template, leaves untouched


def test_per_node_patches_round_trip():
    scn = scenarios.build("clos_summary")
    assert set(scn.patches) == {"spine1", "spine2"}
    for node, diff in scn.patches.items():
        assert apply_unified_diff(scn.pre_configs[node], diff) == scn.post_configs()[node]


def test_summary_originated_discard_backed_on_both_spines():
    post = scenarios.build("clos_summary").post_configs()
    for spine in ("spine1", "spine2"):
        cfg = post[spine]
        # the covering /8 is originated into BGP ...
        assert "network 10.0.0.0/8" in cfg
        # ... backed by a discard static so it always stays up (the trap)
        assert "ip route 10.0.0.0/8 blackhole" in cfg


def test_specific_suppressed_outbound_on_both_spines():
    post = scenarios.build("clos_summary").post_configs()
    for spine in ("spine1", "spine2"):
        cfg = post[spine]
        # an outbound prefix-list denies the more-specific /24 (advertise the
        # summary INSTEAD of the specific toward the leaves)
        assert "ip prefix-list SUMMARIZE_OUT seq 5 deny 10.3.0.0/24" in cfg
        assert "route-map SUMMARIZE_OUT out" in cfg


def test_leaf3_still_originates_specific():
    # leaf3 is untouched: it still originates the real /24 (the only true path).
    scn = scenarios.build("clos_summary")
    assert "network 10.3.0.0/24" in scn.pre_configs["leaf3"]
    assert scn.post_configs()["leaf3"] == scn.pre_configs["leaf3"]


def test_probes_cover_blast_and_control():
    scn = scenarios.build("clos_summary")
    flows = set(scn.forwarding_flows)
    host = base.SERVER_IP + "/32"
    # the two ECMP-capable remote leaves are probed (each blackholes ~1/2)
    assert ("leaf1", host) in flows
    assert ("leaf2", host) in flows
    # negative control: leaf3 serves the host connected
    assert ("leaf3", host) in flows
    # probes target the real host /32, not the bare /24 network address
    assert all(d.endswith("/32") for (_s, d) in flows)
    assert set(scn.reachability_flows) == flows


def test_setwise_forwarding_enabled():
    # partial (1/n) ECMP blackhole -> must score the all-traces SET invariant
    scn = scenarios.build("clos_summary")
    assert scn.forwarding_setwise is True


def test_prompt_does_not_leak_outcome():
    # AUTHORING RULE: the text shown to the model states ONLY the config edit + the
    # policy intent — never the routing OUTCOME.
    scn = scenarios.build("clos_summary")
    shown = (scn.description + " " + scn.intents_text).lower()
    for leak in ("blackhole via", "blackholes", "null_routed", "masks the failure",
                 "drops at spine2", "unreachable via", "ecmp onto spine2"):
        assert leak not in shown
    # it MUST state the policy intent and the edit
    assert "10.0.0.0/8" in scn.description
    assert "reachable" in scn.intents_text.lower()


def test_watched_includes_specific_and_summary():
    scn = scenarios.build("clos_summary")
    assert base.SERVER_PREFIX in scn.watched_prefixes
    assert base.SUMMARY_PREFIX in scn.watched_prefixes
