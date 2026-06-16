"""Pin the synthetic fake ground truth to the LIVE ExtendedOracle key sets.

The zero-API sanity gate (scripts/run_sweep.py --oracle fake) grades models
against ``fake_oracle.fake_ground_truth``. Per CLAUDE.md rule 5 the LIVE
``ExtendedOracle.compute`` is the source of truth, so the fake GT MUST mirror it
exactly — otherwise the offline gate validates the pipeline against a fiction and a
fake/live divergence silently re-enters (audit 2026-06-15, finding M7).

These tests pin three hand-authored scenarios whose fake branches had drifted from
the live oracle:

  * clos_summary — forwarding anomaly node was the flow SOURCE (must be the DROPPING
    node spine2 = change_target); the D2 specific-/24 loss was OMITTED entirely.
  * leak_ms      — forwarding anomaly used the flow SOURCE + kind=blackhole (must be
    the leaker = change_target + kind=null_routed, matching the live LPM blackhole).
  * scale_deagg  — D2 lost the wrong prefix on one node only (must be the /16
    supernet on BOTH the edge and the upstream — 2 rows, not 1).

The expected key sets below are LITERALS captured from the live oracle
(batfish/allinone @ sha256:09817554db90, the pinned :nethelm digest) on 2026-06-15
across multiple fresh Batfish networks (byte-identical). The test does NOT call
Batfish — it is a pure structural pin so the bugs cannot regress, and it runs in
the zero-dependency unit suite. If the live oracle legitimately changes, RE-CAPTURE
these literals from the live run (see /tmp capture in the M7 fix) and update here —
do not weaken the assertion.
"""

from __future__ import annotations

from netbrace.core.dimensions import EXT_ELEMENT_TYPES
from netbrace.reporting.fake_oracle import fake_ground_truth
from netbrace.tasks.safety import scenarios


def _full(expected_nonempty: dict[str, set[str]]) -> dict[str, set[str]]:
    """Expand a sparse {dim: keys} spec into the full 10-dimension key-set dict
    (every dimension present; unlisted dimensions are the empty set), so the
    assertion is EXACT — it catches both a missing key AND a spurious one."""
    ks = {t: set() for t in EXT_ELEMENT_TYPES}
    for dim, keys in expected_nonempty.items():
        assert dim in ks, f"unknown dimension {dim!r}"
        ks[dim] = set(keys)
    return ks


# --------------------------------------------------------------------------- #
# LIVE-CAPTURED expected key sets (literals; no Batfish in the test).
# Captured 2026-06-15 from ExtendedOracle.compute on the pinned :nethelm digest.
# --------------------------------------------------------------------------- #

# clos_summary: change_target = spine2 (the dropping spine). The specific /24
# (10.3.0.0/24) leaves the two remote leaves (leaf1, leaf2) AND spine2; the /8
# summary is ADDED and never appears in D2. D7 null-routes at spine2.
CLOS_SUMMARY_LIVE = _full({
    "prefixes": {
        "route|node=leaf1|vrf=default|prefix=10.3.0.0/24",
        "route|node=leaf2|vrf=default|prefix=10.3.0.0/24",
        "route|node=spine2|vrf=default|prefix=10.3.0.0/24",
    },
    "forwarding": {
        "anomaly|null_routed|node=spine2|vrf=default|dst=10.3.0.1/32",
    },
})

# leak_ms: change_target = leaker (the dropping node, by LPM). transit loses
# reachability to the victim host; the leaker null-routes it (NOT a blackhole, NOT
# at the source). D1/D2 stay empty (the leak ADDS a prefix).
LEAK_MS_LIVE = _full({
    "reachability": {
        "reach|src=transit|dst=203.0.113.1/32|vrf=default",
    },
    "forwarding": {
        "anomaly|null_routed|node=leaker|vrf=default|dst=203.0.113.1/32",
    },
})

# scale_deagg: the covering /16 supernet leaves BOTH the edge and the upstream
# RIBs (2 rows). The constituent /24s are ADDED, never in D2. D8 fib overflow on
# the budgeted edge.
SCALE_DEAGG_LIVE = _full({
    "prefixes": {
        "route|node=edge|vrf=default|prefix=100.64.0.0/16",
        "route|node=upstream|vrf=default|prefix=100.64.0.0/16",
    },
    "scale": {
        "scale|node=edge|resource=fib",
    },
})

# ecmp4 (registry key "ecmp"): the SOLE D5 instance. The live oracle fires D5
# redundancy (ECMP width drop at src) and leaves D3 EMPTY. The old fake branch
# emitted D3 instead, so the offline gate never tested D5 (design-lens M-1).
ECMP4_LIVE = _full({
    "redundancy": {
        "redundancy|node=src|vrf=default|prefix=10.0.0.4/32",
    },
})

# waypoint4 (registry key "waypoint"): D4 waypoint, D3 empty. Old branch emitted D3
# (design-lens M-2).
WAYPOINT4_LIVE = _full({
    "waypoint": {
        "waypoint|src=src|dst=10.0.0.4/32|via=way|vrf=default",
    },
})

# blackhole (registry key "blackhole", scn.name="square4"): removing r1's static to
# r4's loopback severs the loopback-sourced r1<->r4 iBGP session (D1x2) AND blackholes
# the data plane (D2+D3+D7). Old branch emitted D3-only (design-lens M-5; the radius
# was corrected to D1x2+D2+D3+D7 in commit c7c12c1).
SQUARE4_BLACKHOLE_LIVE = _full({
    "sessions": {
        "bgp|vrf=default|node=r1|peer_ip=10.0.0.4",
        "bgp|vrf=default|node=r4|peer_ip=10.0.0.1",
    },
    "prefixes": {
        "route|node=r1|vrf=default|prefix=10.0.0.4/32",
    },
    "reachability": {
        "reach|src=r1|dst=10.0.0.4/32|vrf=default",
    },
    "forwarding": {
        "anomaly|blackhole|node=r1|vrf=default|dst=10.0.0.4/32",
    },
})


def _fake(name: str) -> dict[str, set[str]]:
    return {t: set(v) for t, v in fake_ground_truth(scenarios.build(name)).items()}


def test_fake_clos_summary_matches_live_oracle():
    assert _fake("clos_summary") == CLOS_SUMMARY_LIVE


def test_fake_leak_ms_matches_live_oracle():
    assert _fake("leak_ms") == LEAK_MS_LIVE


def test_fake_scale_deagg_matches_live_oracle():
    assert _fake("scale_deagg") == SCALE_DEAGG_LIVE


# --------------------------------------------------------------------------- #
# Targeted regression guards for each specific M7 bug (so a future edit that
# re-breaks one branch fails with a pointed message, not just an opaque dict diff).
# --------------------------------------------------------------------------- #
def test_clos_summary_anomaly_node_is_dropping_node_not_source():
    """The forwarding anomaly node must be the DROPPING node (change_target=spine2),
    never the flow source (leaf1)."""
    scn = scenarios.build("clos_summary")
    ks = fake_ground_truth(scn)
    fwd = ks["forwarding"]
    assert fwd == {f"anomaly|null_routed|node={scn.change_target}|vrf=default|dst=10.3.0.1/32"}
    assert not any("node=leaf1" in k for k in fwd), "anomaly must NOT be at the source leaf1"


def test_clos_summary_d2_present_with_specific_not_summary():
    """D2 must fire on the specific /24 (not omitted, not the /8 summary)."""
    ks = fake_ground_truth(scenarios.build("clos_summary"))
    assert ks["prefixes"], "D2 must not be empty (it was omitted before the fix)"
    assert all("prefix=10.3.0.0/24" in k for k in ks["prefixes"])
    assert not any("10.0.0.0/8" in k for k in ks["prefixes"]), "the /8 summary is ADDED, not in D2"


def test_leak_ms_anomaly_is_null_routed_at_leaker():
    """The leak blackhole must be null_routed AT the leaker (change_target), not a
    'blackhole' at the source (transit)."""
    scn = scenarios.build("leak_ms")
    ks = fake_ground_truth(scn)
    fwd = ks["forwarding"]
    assert fwd == {f"anomaly|null_routed|node={scn.change_target}|vrf=default|dst=203.0.113.1/32"}
    assert not any("blackhole" in k for k in fwd), "kind must be null_routed (LPM discard), not blackhole"
    assert not any("node=transit" in k for k in fwd), "drop is at the leaker, not the source transit"


def test_scale_deagg_supernet_lost_on_both_nodes():
    """The /16 supernet must leave BOTH nodes' RIBs (2 rows), and the /24s must NOT
    appear in D2 (they are added, not lost)."""
    scn = scenarios.build("scale_deagg")
    ks = fake_ground_truth(scn)
    assert ks["prefixes"] == {
        "route|node=edge|vrf=default|prefix=100.64.0.0/16",
        "route|node=upstream|vrf=default|prefix=100.64.0.0/16",
    }
    assert len(ks["prefixes"]) == 2, "supernet must be lost on BOTH nodes, not 1"
    assert all("100.64.0.0/16" in k for k in ks["prefixes"]), "only the /16, never a /24"


# --------------------------------------------------------------------------- #
# Design-lens M-1/M-2/M-5: the ("square4","ecmp4","waypoint4") branch used to emit
# D3-only for the two SOLE-dimension validators (ecmp4=D5, waypoint4=D4) and the
# corrected blackhole (D1x2+D2+D3+D7) — so the offline `--oracle fake` gate never
# tested those dimensions. These pin the fix to the live oracle.
# --------------------------------------------------------------------------- #
def test_fake_ecmp4_matches_live_oracle():
    assert _fake("ecmp") == ECMP4_LIVE


def test_fake_waypoint4_matches_live_oracle():
    assert _fake("waypoint") == WAYPOINT4_LIVE


def test_fake_square4_blackhole_matches_live_oracle():
    assert _fake("blackhole") == SQUARE4_BLACKHOLE_LIVE


def test_ecmp4_fires_d5_redundancy_not_d3():
    """The sole D5 instance must emit redundancy, with D3 reachability EMPTY."""
    ks = fake_ground_truth(scenarios.build("ecmp"))
    assert ks["redundancy"] == {"redundancy|node=src|vrf=default|prefix=10.0.0.4/32"}
    assert not ks["reachability"], "ecmp4 fake GT must not emit D3 (the old offline-gate bug)"


def test_waypoint4_fires_d4_not_d3():
    """The sole D4 instance must emit waypoint, with D3 reachability EMPTY."""
    ks = fake_ground_truth(scenarios.build("waypoint"))
    assert ks["waypoint"], "waypoint4 must emit D4 waypoint"
    assert not ks["reachability"], "waypoint4 fake GT must not emit D3 (the old bug)"


def test_square4_blackhole_fires_full_radius_not_d3_only():
    """The blackhole must emit D1x2 + D2 + D3 + D7, not the old D3-only simplification."""
    ks = fake_ground_truth(scenarios.build("blackhole"))
    assert len(ks["sessions"]) == 2, "D1 = both endpoints of the severed r1<->r4 session"
    assert ks["prefixes"] and ks["forwarding"], "D2 + D7 must fire (were empty before the fix)"
