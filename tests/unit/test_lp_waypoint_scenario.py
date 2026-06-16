"""Structural tests for lp_waypoint (Class 5: LOCAL_PREF-driven D4) — no Batfish."""
from __future__ import annotations

from netbrace.tasks.safety import scenarios
from netbrace.tasks.safety import baseline_lp_waypoint as base
from netbrace.topology.patches import apply_unified_diff


def test_registered():
    assert "lp_waypoint" in scenarios.REGISTRY


def test_builds_internal_as_with_external_customer():
    scn = scenarios.build("lp_waypoint")
    assert scn.change_target == "alt"
    assert set(scn.nodes) == {"src", "way", "alt", "dst"}
    # internal AS65000 for src/way/alt; external customer AS65004 for dst
    assert base.ASN == {"src": 65000, "way": 65000, "alt": 65000, "dst": 65004}


def test_patch_round_trips_on_alt_only():
    scn = scenarios.build("lp_waypoint")
    pre, post = scn.pre_configs, scn.post_configs()
    changed = [n for n in scn.nodes if post[n] != pre[n]]
    assert changed == ["alt"]
    assert apply_unified_diff(pre["alt"], scn.patch) == post["alt"]


def test_post_raises_alt_localpref_above_way():
    """The change sets a higher local-pref on the alt (bypass) path."""
    scn = scenarios.build("lp_waypoint")
    pre_alt = scn.pre_configs["alt"]
    post_alt = scn.post_configs()["alt"]
    # pre: alt=100 (loses to way=200); post: alt=300 (beats way=200)
    assert "set local-preference 100" in pre_alt
    assert "set local-preference 300" in post_alt
    assert "set local-preference 100" not in post_alt
    # way's preference is untouched by the change (the gap stays STRICT)
    assert "set local-preference 200" in scn.pre_configs["way"]
    assert scn.post_configs()["way"] == scn.pre_configs["way"]


def test_strict_preference_no_tie_pre_and_post():
    """Both snapshots have a STRICT LP gap -> single best path, no ECMP tie."""
    scn = scenarios.build("lp_waypoint")
    # pre: way=200 > alt=100 (strict);  post: alt=300 > way=200 (strict)
    assert "set local-preference 200" in scn.pre_configs["way"]
    assert "set local-preference 100" in scn.pre_configs["alt"]
    assert "set local-preference 300" in scn.post_configs()["alt"]
    # no maximum-paths anywhere -> default 1 -> no multipath
    for cfg in scn.pre_configs.values():
        assert "maximum-paths" not in cfg
    for cfg in scn.post_configs().values():
        assert "maximum-paths" not in cfg


def test_no_session_or_prefix_machinery_touched():
    """The change is attribute-only: no neighbor/network statement is added/removed."""
    scn = scenarios.build("lp_waypoint")
    pre_alt = scn.pre_configs["alt"]
    post_alt = scn.post_configs()["alt"]
    # neighbor count and network statements are identical pre/post
    assert pre_alt.count("neighbor ") == post_alt.count("neighbor ")
    assert pre_alt.count("network ") == post_alt.count("network ")
    # no session-resetting primitives in the patch
    assert "remote-as" not in scn.patch
    assert "shutdown" not in scn.patch


def test_customer_prefix_originated_and_dual_homed():
    """dst originates the /24 and peers eBGP with BOTH egress routers."""
    scn = scenarios.build("lp_waypoint")
    dst = scn.pre_configs["dst"]
    assert "network 203.0.113.0/24" in dst
    # eBGP to way (192.0.2.9) and alt (192.0.2.13) link IPs
    assert "neighbor 192.0.2.9 remote-as 65000" in dst
    assert "neighbor 192.0.2.13 remote-as 65000" in dst
    # the change does not touch dst's origin -> D2 precondition
    assert scn.post_configs()["dst"] == dst


def test_waypoint_intent_and_reachability_probes():
    scn = scenarios.build("lp_waypoint")
    host = base.CUSTOMER_IP + "/32"
    # D4 intent: src -> customer host MUST transit `way`
    assert ("src", host, "way") in scn.waypoint_intents
    # D3 proof flow: src must still reach the customer host (probe present)
    assert ("src", host) in scn.reachability_flows
    # probes target the real host /32, not the bare /24 network address
    assert all(d.endswith("/32") for (_s, d, _w) in scn.waypoint_intents)


def test_src_resolves_both_egress_next_hops():
    """src has static routes to BOTH dst-side egress link /30s, so the eBGP
    next-hop on each iBGP-learned customer route resolves -> a route via EACH
    egress exists and the choice is purely the LOCAL_PREF best-path decision."""
    scn = scenarios.build("lp_waypoint")
    src = scn.pre_configs["src"]
    assert "ip route 192.0.2.8/30 192.0.2.2" in src   # way egress link via way
    assert "ip route 192.0.2.12/30 192.0.2.6" in src  # alt egress link via alt
    # the change does not touch src's resolution -> both stay resolvable post
    assert scn.post_configs()["src"] == src


def test_watched_includes_customer_and_loopbacks():
    scn = scenarios.build("lp_waypoint")
    assert base.CUSTOMER_PREFIX in scn.watched_prefixes
    for n in ("1", "2", "3", "4"):
        assert f"10.0.0.{n}/32" in scn.watched_prefixes
