"""Synthetic, deterministic ground truth for ZERO-Batfish sweep validation.

The real ground truth is ``netbrace.batfish.extended_oracle.ExtendedOracle.compute``
(needs a pinned Batfish). To validate the SWEEP PLUMBING (two-stage aggregation,
baselines, splits, modal_by_class, the trap metric) with no Docker and no API, this
module emits ground truth that is STRUCTURALLY representative of each scenario class
— it is NOT Batfish-accurate and must NEVER be used for a reported number. It exists
only so ``scripts/run_sweep.py --oracle fake`` exercises the whole pipeline offline.

It reads a ``Scenario`` (the same dataclass the real oracle consumes) and infers the
expected blast structure from the public, documented class semantics:

  * Class-1 templated IPC (name starts ``gen_ipc_``): decode the IpcSpec axes from
    the dims_label and emit the documented GT (plain -> D2+D3; static -> D9;
    aggregate -> D2 on the /25s + D10 te_pin; filtered=all -> all k clients).
  * Hand-authored scenarios: a small per-name table of the documented GT shape.

D1 (sessions) is ALWAYS empty here — that is the NetHELM trap invariant (sessions
stay ESTABLISHED), so naive_session_loss reliably trips false_session_alarm and a
silent/empty predictor does not.
"""

from __future__ import annotations

from netbrace.core.dimensions import EXT_ELEMENT_TYPES
from netbrace.core.schemas import canon_node, canon_prefix
from netbrace.reporting.baselines import KeySets, empty_keysets


def _route_key(node: str, prefix: str) -> str:
    return f"route|node={canon_node(node)}|vrf=default|prefix={canon_prefix(prefix)}"


def _reach_key(node: str, prefix: str) -> str:
    return f"reach|src={canon_node(node)}|dst={canon_prefix(prefix)}|vrf=default"


def _bgp_key(node: str, prefix: str) -> str:
    return f"bgp_withdrawn|node={canon_node(node)}|vrf=default|network={canon_prefix(prefix)}"


def _intent_te_key(src: str, dst: str) -> str:
    return f"intent|kind=te_pin|src={canon_node(src)}|dst={canon_prefix(dst)}"


def _intent_key(kind: str, src: str, dst: str) -> str:
    return f"intent|kind={kind}|src={canon_node(src)}|dst={canon_prefix(dst)}"


def _longest_non_host_prefix(prefixes) -> str | None:
    """The MOST-SPECIFIC (longest mask) non-/32 watched prefix.

    The hand-authored ``cust`` heuristic (``next reversed ... not endswith /32``)
    picks the LAST-listed non-host prefix, which is wrong when a watch set lists a
    covering aggregate AFTER the specific (clos_summary watches the specific
    10.3.0.0/24 then the /8 summary; reversed -> the /8). The blast lands on the
    specific the summary MASKS, so we select by longest mask, with the network
    address as a deterministic tie-break. Mirrors the live oracle, which loses the
    SPECIFIC /24 from the leaf RIBs (the /8 is ADDED, never in D2)."""
    nets = [p for p in (prefixes or []) if not p.endswith("/32")]
    if not nets:
        return None
    return max(nets, key=lambda p: (int(p.rsplit("/", 1)[1]), p))


def _parse_gen_label(name: str) -> dict:
    """gen_ipc_k<k>-<filtered>-<dir>-<prefix>-<match>_s<seed> -> axis dict."""
    body = name[len("gen_ipc_"):].rsplit("_s", 1)[0]
    k_tok, filtered, direction, prefix, match = body.split("-")
    return {
        "k": int(k_tok[1:]),
        "filtered": filtered,
        "direction": direction,
        "prefix": prefix,
        "match": match,
    }


def fake_ground_truth(scn) -> KeySets:
    """Return synthetic per-dimension key sets for a Scenario (D1 always empty)."""
    ks = empty_keysets()
    name = getattr(scn, "name", "")

    if name.startswith("gen_ipc_"):
        return _fake_gen_ipc(scn)
    if name.startswith("gen_leak_"):
        return _fake_gen_leak(scn)
    if name.startswith("gen_lp_"):
        return _fake_gen_lp(scn)
    if name.startswith("gen_scale_"):
        return _fake_gen_scale(scn)

    # Hand-authored scenarios: documented GT shape (D1 always empty -> the trap).
    return _fake_handauthored(scn)


def _affected_clients(scn, axes) -> list[str]:
    # nodes are ordered [rr, client_1..client_k, origin]; clients = nodes[1:1+k].
    k = axes["k"]
    clients = scn.nodes[1 : 1 + k]
    return clients if axes["filtered"] == "all" else clients[:1]


def _fake_gen_ipc(scn) -> KeySets:
    ks = empty_keysets()
    axes = _parse_gen_label(scn.name)
    affected = _affected_clients(scn, axes)

    # the customer /24 is the last watched prefix that is NOT a /32 loopback.
    cust = next((p for p in reversed(scn.watched_prefixes)
                 if not p.endswith("/32")), None)
    if cust is None:
        return ks

    if axes["prefix"] == "static":
        # control-plane only: D9 fires, D2/D3 silent.
        for c in affected:
            ks["bgp_withdrawn"].add(_bgp_key(c, cust))
        return ks

    if axes["prefix"] == "aggregate":
        # /24 survives; the two /25 more-specifics are withdrawn -> D2 on /25s + D10.
        base = cust.split("/")[0].rsplit(".", 1)[0]
        low, high = f"{base}.0/25", f"{base}.128/25"
        for c in affected:
            ks["prefixes"].add(_route_key(c, low))
            ks["prefixes"].add(_route_key(c, high))
            ks["intent"].add(_intent_te_key(c, low))
            ks["intent"].add(_intent_te_key(c, high))
        return ks

    # plain: coupled D2 + D3 on the affected client(s).
    for c in affected:
        ks["prefixes"].add(_route_key(c, cust))
        ks["reachability"].add(_reach_key(c, cust))
    return ks


def _gen_label_axes(name: str, prefix: str) -> list[str]:
    """gen_<gen>_<axis1>-<axis2>_s<seed> -> [axis1, axis2]."""
    body = name[len(prefix):].rsplit("_s", 1)[0]
    return body.split("-")


def _fake_gen_leak(scn) -> KeySets:
    """Class-2 route leak (generator_leak): documented GT structure.

    ms_blackhole -> per leaked /25: D3 reach loss at the transit + D7 null_routed
    at the leaker (D1=D2=∅ — the thesis). ms_reroute -> traffic still delivered
    (D3/D7 silent); the victim bypass fires D4 + the D10 waypoint invariant.
    The leaked /25s are read off ``watched_prefixes`` (the generator watches
    exactly the leaked halves); the first host of a /25 is the probe target.
    """
    ks = empty_keysets()
    kind, _scope = _gen_label_axes(scn.name, "gen_leak_")
    transit, leaker = scn.nodes[1], scn.nodes[2]

    if kind == "ms_reroute":
        for (s, d, w) in scn.waypoint_intents:
            ks["waypoint"].add(
                f"waypoint|src={canon_node(s)}|dst={canon_prefix(d)}|via={canon_node(w)}|vrf=default")
        for inv in scn.intent_invariants:
            ks["intent"].add(_intent_key(inv.kind, inv.src or "*", inv.dst))
        return ks

    # ms_blackhole
    for p in scn.watched_prefixes:
        if not p.endswith("/25"):
            continue
        base = p.split("/")[0]
        octets = base.rsplit(".", 1)
        host = f"{octets[0]}.{int(octets[1]) + 1}/32"
        ks["reachability"].add(_reach_key(transit, host))
        ks["forwarding"].add(
            f"anomaly|null_routed|node={canon_node(leaker)}|vrf=default|dst={canon_prefix(host)}")
    return ks


def _fake_gen_lp(scn) -> KeySets:
    """Class-5 attribute path-shift (generator_lp): bypass -> D4 only; no_op ->
    COMPLETELY EMPTY (the calibration trap: the correct answer is no blast)."""
    ks = empty_keysets()
    _knob, effect = _gen_label_axes(scn.name, "gen_lp_")
    if effect == "no_op":
        return ks
    for (s, d, w) in scn.waypoint_intents:
        ks["waypoint"].add(
            f"waypoint|src={canon_node(s)}|dst={canon_prefix(d)}|via={canon_node(w)}|vrf=default")
    return ks


def _fake_gen_scale(scn) -> KeySets:
    """Class-8 de-agg overflow (generator_scale): D8 fires iff margin is over_*;
    D2 = the supernet (shortest watched prefix) lost on BOTH nodes iff withdrawn;
    under -> D8 silent (the must-actually-count trap)."""
    ks = empty_keysets()
    margin, fate = _gen_label_axes(scn.name, "gen_scale_")
    if margin.startswith("over"):
        for node, limits in (scn.resource_limits or {}).items():
            for res in limits:
                ks["scale"].add(f"scale|node={canon_node(node)}|resource={res}")
    if fate == "withdrawn":
        nets = [p for p in scn.watched_prefixes if not p.endswith("/32")]
        if nets:
            supernet = min(nets, key=lambda p: int(p.rsplit("/", 1)[1]))
            for node in scn.nodes:
                ks["prefixes"].add(_route_key(node, supernet))
    return ks


def _fake_handauthored(scn) -> KeySets:
    """Documented GT shape for the hand-authored registry scenarios."""
    ks = empty_keysets()
    name = scn.name
    tgt = scn.change_target
    cust = next((p for p in reversed(scn.watched_prefixes)
                 if not p.endswith("/32")), None)

    if name in ("ipc3",):
        # flagship: D2 + D3 on the access client (r2).
        client = scn.reachability_flows[0][0] if scn.reachability_flows else tgt
        if cust:
            ks["prefixes"].add(_route_key(client, cust))
            ks["reachability"].add(_reach_key(client, cust))
    elif name == "ipc3_static":
        client = scn.reachability_flows[0][0] if scn.reachability_flows else tgt
        if cust:
            ks["bgp_withdrawn"].add(_bgp_key(client, cust))
    elif name == "ipc_fanout":
        # multi-node: D2 + D3 on three clients.
        clients = sorted({s for (s, _d) in scn.reachability_flows})[:3]
        for c in clients:
            if cust:
                ks["prefixes"].add(_route_key(c, cust))
                ks["reachability"].add(_reach_key(c, cust))
    elif name == "ipc_aggregate":
        for inv in scn.intent_invariants:
            ks["intent"].add(_intent_te_key(inv.src or "*", inv.dst))
            ks["prefixes"].add(_route_key(inv.src or tgt, inv.dst))
    elif name == "leak_ms":
        # D3 reachability loss at the flow SOURCE (transit) + D7 forwarding anomaly
        # at the DROPPING node (the leaker, scn.change_target), NOT the source —
        # the more-specific /25 leak pulls transit's traffic to the leaker by LPM
        # and it is null-routed THERE (the leaker's discard static). Live oracle:
        # node=leaker, kind=null_routed (NOT blackhole). D1/D2 stay empty (the leak
        # ADDS a prefix, so nothing is "lost"). The change_target IS the leaker, so
        # the dropping node is derived from the scenario, not a name literal. This
        # now matches the generated twin (_fake_gen_leak, which uses `leaker`).
        for (s, d) in (scn.forwarding_flows or [])[:1]:
            ks["forwarding"].add(
                f"anomaly|null_routed|node={canon_node(tgt)}|vrf=default|dst={canon_prefix(d)}")
            ks["reachability"].add(_reach_key(s, d))
    elif name == "lp_waypoint":
        # only D4 waypoint fires.
        for (s, d, w) in scn.waypoint_intents:
            ks["waypoint"].add(
                f"waypoint|src={canon_node(s)}|dst={canon_prefix(d)}|via={canon_node(w)}|vrf=default")
    elif name == "clos_summary":
        # D7 forwarding anomaly at the DROPPING node (spine2 = scn.change_target),
        # NOT the flow source: the summary masks spine2's missing path, so the ECMP
        # path via spine2 null-routes the server host. AND D2: the SPECIFIC /24
        # (the longest non-/32 watched prefix; the /8 summary is ADDED, never in D2)
        # leaves the RIBs of the two REMOTE leaves AND spine2. The remote leaves are
        # the forwarding-flow sources EXCEPT the trailing negative-control source
        # (leaf3, which serves the host connected and is listed last by authoring
        # convention). Derived from the scenario object, no node-name literals.
        specific = _longest_non_host_prefix(scn.watched_prefixes)
        flows = scn.forwarding_flows or []
        for (s, d) in flows[:1]:
            ks["forwarding"].add(
                f"anomaly|null_routed|node={canon_node(tgt)}|vrf=default|dst={canon_prefix(d)}")
        if specific:
            remote_leaves = [s for (s, _d) in flows[:-1]]  # drop the trailing neg control
            for node in remote_leaves + [tgt]:
                ks["prefixes"].add(_route_key(node, specific))
    elif name == "scale_deagg":
        # D8 scale overflow on the budgeted node(s) + the D2 supernet SWAP. The
        # benign loss signal is the covering /16 supernet (the SHORTEST-mask non-/32
        # watched prefix) leaving BOTH nodes' RIBs — the upstream stops originating
        # it and the edge stops learning it (live oracle: 2 rows, edge AND upstream,
        # not 1). The constituent /24s are ADDED, not lost, so they never appear in
        # D2. Derived from the scenario: the supernet by shortest mask, the two
        # losing nodes = scn.nodes (no name literals).
        for node, limits in (scn.resource_limits or {}).items():
            for res in limits:
                ks["scale"].add(f"scale|node={canon_node(node)}|resource={res}")
        supernet = None
        nets = [p for p in scn.watched_prefixes if not p.endswith("/32")]
        if nets:
            supernet = min(nets, key=lambda p: (int(p.rsplit("/", 1)[1]), p))
        if supernet:
            for node in scn.nodes:
                ks["prefixes"].add(_route_key(node, supernet))
    elif name == "mgmt_lockout":
        # mgmt-plane lockout: D1/D2 empty (the watched set survives); each managed
        # device's mgmt path is a D3 reachability loss AND a D10 management-
        # reachability intent violation. The reachability flows[0:2] are the two
        # jump->mgmt-IP losses; the intent invariants carry the canonical (src,dst).
        for (s, d) in (scn.reachability_flows or [])[:2]:
            ks["reachability"].add(_reach_key(s, d))
        for inv in scn.intent_invariants:
            ks["intent"].add(_intent_key(inv.kind, inv.src or "*", inv.dst))
    elif name == "ecmp4":
        # D5 redundancy loss — the SOLE D5 instance. The live oracle fires
        # `redundancy` (ECMP width drop) and leaves D3 EMPTY: reachability_flows here
        # is a silent anchor (== redundancy_targets), NOT a reachability effect. The
        # old branch emitted D3 instead, so the offline `--oracle fake` gate never
        # exercised the redundancy keyset for the only scenario that validates it
        # (audit 2026-06-15 design-lens M-1). Mirror the live oracle.
        for (node, prefix) in (scn.redundancy_targets or []):
            ks["redundancy"].add(
                f"redundancy|node={canon_node(node)}|vrf=default|prefix={canon_prefix(prefix)}")
    elif name == "waypoint4":
        # D4 waypoint — NOT D3. The live oracle fires `waypoint` and leaves D3 empty
        # (reachability_flows is the silent anchor). Old branch emitted D3, so the
        # offline gate never tested D4 for this sole-D4 instance (design-lens M-2).
        for (s, d, w) in (scn.waypoint_intents or []):
            ks["waypoint"].add(
                f"waypoint|src={canon_node(s)}|dst={canon_prefix(d)}|via={canon_node(w)}|vrf=default")
    elif name == "square4":
        # The blackhole-on-square4 scenario (scn.name="square4", scenario_blackhole.py).
        # Removing r1's static to r4's loopback (10.0.0.4) both blackholes the data
        # plane AND severs the loopback-sourced r1<->r4 iBGP session (both endpoints).
        # Live oracle (radius corrected in commit c7c12c1): D1x2 + D2 + D3 + D7. The old
        # D3-only branch was a stale simplification that broke the offline gate after
        # the radius was fixed (design-lens M-5). This is a FIXED hand-authored scenario
        # (frozen square4 baseline, no randomization), so the two session endpoints are
        # stable literals; D2/D3/D7 derive from the forwarding flow.
        ks["sessions"].add("bgp|vrf=default|node=r1|peer_ip=10.0.0.4")
        ks["sessions"].add("bgp|vrf=default|node=r4|peer_ip=10.0.0.1")
        for (s, d) in (scn.forwarding_flows or [])[:1]:
            ks["prefixes"].add(_route_key(s, d))         # D2: r1 loses 10.0.0.4/32
            ks["reachability"].add(_reach_key(s, d))     # D3
            ks["forwarding"].add(                        # D7
                f"anomaly|blackhole|node={canon_node(s)}|vrf=default|dst={canon_prefix(d)}")
    return ks
