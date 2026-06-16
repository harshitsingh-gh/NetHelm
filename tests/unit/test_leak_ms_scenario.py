"""Structural tests for leak_ms (Class 2: more-specific route leak) — no Batfish."""
from __future__ import annotations

from netbrace.tasks.safety import scenarios
from netbrace.tasks.safety import baseline_leak_ms as base
from netbrace.topology.patches import apply_unified_diff


def test_registered():
    assert "leak_ms" in scenarios.REGISTRY


def test_builds_three_as_ebgp_chain():
    scn = scenarios.build("leak_ms")
    assert scn.change_target == "leaker"
    assert set(scn.nodes) == {"victim", "transit", "leaker"}
    # distinct ASNs (the multi-AS property that makes this a route leak)
    assert sorted(base.ASN.values()) == [65001, 65002, 65003]


def test_patch_round_trips_on_leaker_only():
    scn = scenarios.build("leak_ms")
    pre, post = scn.pre_configs, scn.post_configs()
    changed = [n for n in scn.nodes if post[n] != pre[n]]
    assert changed == ["leaker"]
    assert apply_unified_diff(pre["leaker"], scn.patch) == post["leaker"]


def test_post_adds_more_specific_and_blackhole():
    post_leaker = scenarios.build("leak_ms").post_configs()["leaker"]
    # the more-specific /25 is originated post-change
    assert "network 203.0.113.0/25" in post_leaker
    # backed by a blackhole static so the leaker has no real path (the trap)
    assert "ip route 203.0.113.0/25 blackhole" in post_leaker
    # the legit /24 is NOT originated by the leaker (it does not serve it)
    assert "network 203.0.113.0/24" not in post_leaker


def test_legit_24_survives_in_baseline_and_post():
    """The victim's /24 origin is untouched -> precondition for D2 = ∅."""
    scn = scenarios.build("leak_ms")
    assert "network 203.0.113.0/24" in scn.pre_configs["victim"]
    assert "network 203.0.113.0/24" in scn.post_configs()["victim"]
    # the change touches only the leaker, so the victim origin cannot be lost
    assert scn.post_configs()["victim"] == scn.pre_configs["victim"]


def test_probes_cover_blast_flow_and_controls():
    scn = scenarios.build("leak_ms")
    flows = set(scn.forwarding_flows)
    victim_host = base.VICTIM_IP + "/32"
    leaker_host = base.LEAKER_IP + "/32"
    # the blackholed flow (transit -> victim host) is probed for D7
    assert ("transit", victim_host) in flows
    # negative controls: leaker's own legit host + victim-as-source
    assert ("transit", leaker_host) in flows
    assert ("victim", victim_host) in flows
    # probes target the real host /32, not the bare /24 network address
    assert all(d.endswith("/32") for (_s, d) in flows)
    # D3 reachability mirrors the forwarding flows
    assert set(scn.reachability_flows) == flows


def test_watched_includes_leak_and_legit_prefixes():
    scn = scenarios.build("leak_ms")
    # the /25 is watched so an ADDED-route report is not penalised, and so the
    # legit /24 can be asserted present (not lost) by the oracle.
    assert base.LEAK_PREFIX in scn.watched_prefixes
    assert base.VICTIM_PREFIX in scn.watched_prefixes
