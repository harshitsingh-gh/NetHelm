"""Class-5 generator — ATTRIBUTE-INDUCED PATH-SHIFT (the `lp_waypoint` mechanism),
re-homed onto an IDIOMATIC ALL-eBGP topology.

This is the parameterized generator for the spine-class-5 "attribute change flips
the best path off the inspection waypoint" trap (docs/oracle_determinism_spec_v1.md
class 5). It is the audit-mandated fix for findings **K3** (N-inflation: generate
held-out variants for more mechanisms) and **M3** (realism: the hand-authored
`lp_waypoint` baseline steers via STATIC routes to *external* /30 next-hops — a
config no operator writes; the network-architect ruled the TRAP is real but the
config must move to an all-eBGP design where eBGP next-hops are DIRECTLY CONNECTED
and NO static crutch is needed). See paper/refs/audit_2026-06-10_publication_safety.md
§2 K3, §3 M3, §5.

Mechanism (unchanged from the documented LLM failure mode — the "sessions don't
drop on LOCAL_PREF/attribute changes" trap, knowledge/corpus/noc/
network_change_management.md + RFC 4271 §8/§9.1.1): an inbound eBGP policy edit at
`src` re-weights the path to a dual-homed customer prefix, flipping `src`'s best
path off the inspection node `way` onto the bypass `alt`. THE TRAP: D1 sessions = ∅
(an attribute change never resets the BGP FSM), D2 prefixes = ∅, D3 reachability =
∅ (the customer stays reachable, just via the wrong egress) — ONLY D4 (waypoint)
fires. A naive model predicts a D1 session drop and/or D2/D3 loss; the oracle says
otherwise.

Topology (4 nodes, ALL eBGP, distinct ASNs, directly-connected next-hops)::

           inbound route-map (the KNOB) on src toward each upstream
        +----------------------------------------------------+
        |                                                    |
      src ---/30--- way (AS_way) ---/30(eBGP)--- dst   (the WAY / inspection path)
   (AS_src) |                                      |
            |                                      |   customer /24
            +---/30--- alt (AS_alt) ---/30(eBGP)---+   (originated by dst,
                                                       dual-homed to way & alt)

  * src is AS_src; it eBGP-peers DIRECTLY (over the /30 link IP, no update-source,
    no multihop — leak_ms doctrine) with both way (AS_way) and alt (AS_alt).
  * way and alt are distinct upstream ASes; each eBGP-peers with dst (AS_dst) over a
    directly-connected /30. dst originates the customer /24 on a dummy host.
  * src learns the customer prefix over BOTH upstreams. The eBGP next-hop on each
    received route is the DIRECTLY-CONNECTED upstream's /30 IP, so it resolves with
    NO static route. This is the whole point of the re-home: zero static next-hop
    plumbing anywhere (contrast the hand-authored baseline_lp_waypoint).
  * src applies an INBOUND route-map on each upstream session (RM_UPLINK1_IN /
    RM_UPLINK2_IN). The baseline steers src's best path onto `way`; the change edits
    one of those inbound maps to flip it onto `alt`.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {lp_raise_alt, lp_drop_way, prepend_way} — three DIFFERENT attribute
    mechanisms that all flip the best path off the waypoint (same D4 GT class), each
    forcing the reader to parse a different construct:
      - lp_raise_alt : baseline LP(way)=200 > LP(alt)=100; the change RAISES the alt
        inbound map's `set local-preference` to 300, so alt now wins (300 > 200).
      - lp_drop_way  : same baseline; the change LOWERS the way inbound map's
        `set local-preference` to 50, so alt now wins (100 > 50). Same outcome,
        opposite edit, different device construct to read.
      - prepend_way  : LOCAL_PREF is EQUAL on both upstreams in the baseline (so the
        best-path decision falls through to AS_PATH length, RFC 4271 §9.1.1 step 4);
        the baseline already prepends `alt`'s inbound path once so `way` (shorter
        AS_PATH) wins. The change adds `set as-path prepend` on the WAY inbound map,
        making way's AS_PATH longer than alt's, so alt wins. Tests reading an
        AS_PATH construct rather than a LOCAL_PREF value.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually flips the best path. D4 fires; D1/D2/D3 = ∅. THE
        trap.
      - no_op  : the SAME KIND of edit applied where it does NOT change the best
        path (raise the LP of the already-preferred way path even higher; lower the
        already-losing alt path; prepend the already-losing alt path more). Ground
        truth is COMPLETELY EMPTY across ALL dimensions — the ultimate calibration
        trap (the model must predict an empty blast radius). The prose is
        indistinguishable in style from a bypass edit; only careful best-path
        reasoning separates them.

That is 3 knobs × 2 effects = 6 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_ipc): ASNs
(4-byte private range), loopback block, link /30 supernet, customer /24, and node
base name are all drawn deterministically from the seed. Same seed ⇒ byte-identical
instance; different seed ⇒ a novel instance even for this public mechanism.

Determinism contract (oracle_determinism_spec_v1.md class 5, STATIC-DET): every
best-path decision is STRICT in both snapshots (a real LP gap, or an AS_PATH-length
gap with equal LP) — exactly one best path at src in each snapshot, no equal-cost
ECMP tie, maximum-paths default 1. Router-ids are pinned to the (randomized)
loopbacks. D4 is scored by ExtendedOracle._waypoint_diff as the all-traces-transit
invariant, never chosen-path identity. NO static routes ⇒ no recursive-next-hop
artifact (the M1 critique of `blackhole` does not apply here).

Public API mirrors generator_ipc:
    generate_lp_suite(n, seed=...)         -> list[Scenario]
    generate_lp_all_combos(seed=...)       -> list[Scenario]   (one per structural combo)
    generate_lp_instance(seed, spec=None)  -> Scenario
    enumerate_specs() / enumerable_count()
"""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass
from typing import Optional

from netbrace.tasks.safety.scenarios import Scenario
from netbrace.topology.patches import apply_unified_diff

# --------------------------------------------------------------------------- #
# Axis value sets (the enumerable space).
# --------------------------------------------------------------------------- #
KNOB_VALUES = ("lp_raise_alt", "lp_drop_way", "prepend_way")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}


@dataclass(frozen=True)
class LpSpec:
    """A point in the Class-5 generator space (the axis tuple, pre-randomization)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[LpSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[LpSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(LpSpec(knob, effect))
    return out


def enumerable_count() -> int:
    """Number of distinct axis combinations (each ×∞ randomized seeds)."""
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). We keep clear of the hand-authored 65000
# family AND draw FOUR DISTINCT ASNs (src/way/alt/dst) so a generated instance never
# collides with the baseline and every AS is genuinely external to every other.
_ASN_LO, _ASN_HI = 4_200_100_000, 4_200_199_999

# Customer-prefix pools (documentation / TEST-NET / RFC-1918 customer space).
_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

# Node base-name pools (string only; topology role is unchanged).
_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    asn: dict[str, int]      # role -> ASN  (roles: src, way, alt, dst)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string


_ROLES = ("src", "way", "alt", "dst")


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    # Four DISTINCT ASNs, one per role.
    asns: list[int] = []
    while len(asns) < 4:
        a = rng.randint(_ASN_LO, _ASN_HI)
        if a not in asns:
            asns.append(a)
    asn = dict(zip(_ROLES, asns))

    # loopback /24: 10.<1-250>.<0-250>.0  (then /32s 10.x.y.N)
    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"

    # link /30 supernet: 192.<0-250>.<0-250>.0  (carve /30s for each link)
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    # customer /24 base (render any {c} placeholder)
    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    # Distinct node names: draw one base, then number by a FIXED role order so the
    # same role always maps to the same string within an instance.
    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    return _Params(asn=asn, loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name=name)


# --------------------------------------------------------------------------- #
# Topology builder: src dual-homed (eBGP) to way + alt, each eBGP to dst.
# Deterministic addressing derived from the randomized blocks.
# Links, fixed order (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    """A concrete, addressed all-eBGP topology for one instance."""

    params: _Params
    spec: LpSpec
    name: dict[str, str]                    # role -> node name
    loopback: dict[str, str]               # role -> "x.y.z.N"
    rid_index: dict[str, int]              # role -> the integer N in the loopback
    # link IPs: ip[(role, peer_role)] = role's IP on the role<->peer /30.
    ip: dict[tuple[str, str], str]
    customer_prefix: str                   # "<net>/24"
    customer_ip: str                       # an address inside it (the .1 host)


def _build_topo(spec: LpSpec, params: _Params) -> _Topo:
    name = dict(params.name)

    # loopbacks/router-ids: src=.1, way=.2, alt=.3, dst=.4
    rid_index = {"src": 1, "way": 2, "alt": 3, "dst": 4}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    # /30 link supernets, one per link, carved from the link block:
    #   link0 src-way  base .0  (src=.1, way=.2)
    #   link1 src-alt  base .4  (src=.5, alt=.6)
    #   link2 way-dst  base .8  (way=.9, dst=.10)
    #   link3 alt-dst  base .12 (alt=.13, dst=.14)
    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    ip: dict[tuple[str, str], str] = {
        ("src", "way"): addr(1), ("way", "src"): addr(2),
        ("src", "alt"): addr(5), ("alt", "src"): addr(6),
        ("way", "dst"): addr(9), ("dst", "way"): addr(10),
        ("alt", "dst"): addr(13), ("dst", "alt"): addr(14),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    return _Topo(
        params=params, spec=spec, name=name, loopback=loopback,
        rid_index=rid_index, ip=ip, customer_prefix=customer_prefix,
        customer_ip=customer_ip,
    )


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, the verified leak_ms format).
# All eBGP, directly-connected /30 peers, NO static routes anywhere.
# --------------------------------------------------------------------------- #
_LINK_MASK = "/30"


def _ifaces_intf_text(
    node_name: str, loopback: str,
    eth_ifaces: list[tuple[str, str]],   # (iface, "ip/mask")
    dummies: list[tuple[str, str]],      # (iface, "ip/mask")
) -> tuple[str, str]:
    """Return (interfaces-stanza-block, frr-interface-stanza-block) for a node."""
    # /etc/network/interfaces-style block (the leak_ms header format).
    ib = [
        node_name, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {loopback}/32", "",
    ]
    for iface, ipm in eth_ifaces:
        ib += [f"auto {iface}", f"iface {iface} inet static", f"    address {ipm}", ""]
    for iface, ipm in dummies:
        ib += [f"auto {iface}", f"iface {iface} inet static", f"    address {ipm}", ""]
    ib += ["# ports.conf --", ""]

    # FRR `interface` stanzas.
    fb = [f"interface lo\n ip address {loopback}/32\n!"]
    for iface, ipm in eth_ifaces:
        fb.append(f"interface {iface}\n ip address {ipm}\n!")
    for iface, ipm in dummies:
        fb.append(f"interface {iface}\n ip address {ipm}\n!")

    return "\n".join(ib) + "\n", "\n".join(fb) + "\n"


def _frr_header(node_name: str) -> str:
    return (
        "frr version 10.6.1\n"
        "frr defaults traditional\n"
        f"hostname {node_name}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


# ---- the inbound steering route-maps on src (the KNOB lives here) ----------- #
# A route-map on src toward each upstream. The baseline values are chosen per knob
# so that `way` is the best path in the PRE state (waypoint satisfied).
def _baseline_rmaps(topo: _Topo) -> tuple[list[str], list[str]]:
    """Return (way_inbound_map_lines, alt_inbound_map_lines) for the baseline."""
    knob = topo.spec.knob
    if knob in ("lp_raise_alt", "lp_drop_way"):
        # LOCAL_PREF steering: way 200 strictly beats alt 100 -> way preferred.
        way = ["route-map RM_UPLINK1_IN permit 10", " set local-preference 200", "!"]
        alt = ["route-map RM_UPLINK2_IN permit 10", " set local-preference 100", "!"]
    else:  # prepend_way
        # Equal LOCAL_PREF (default; made explicit for clarity) so best-path falls
        # through to AS_PATH length. Baseline prepends ALT once -> way's AS_PATH is
        # shorter -> way preferred. The change will prepend WAY to flip it. We prepend
        # src's OWN ASN (the idiomatic inbound-TE technique) using literal-ASN syntax
        # (`set as-path prepend <asn>`), which Batfish's FRR model parses; the
        # `last-as N` shorthand is NOT modeled by Batfish, verified live.
        src_asn = topo.params.asn["src"]
        way = ["route-map RM_UPLINK1_IN permit 10", " set local-preference 100", "!"]
        alt = [
            "route-map RM_UPLINK2_IN permit 10",
            " set local-preference 100",
            f" set as-path prepend {src_asn}",
            "!",
        ]
    return way, alt


def _src_config(topo: _Topo) -> str:
    p = topo.params
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name["src"], topo.loopback["src"], eth, [])
    way_map, alt_map = _baseline_rmaps(topo)

    body = [ib, _frr_header(topo.name["src"]), fb]
    body.append("\n".join(way_map) + "\n")
    body.append("\n".join(alt_map) + "\n")
    body.append(f"router bgp {p.asn['src']}\n")
    body.append(f" bgp router-id {topo.loopback['src']}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback['src']}/32\n")
    body.append(f"  neighbor {topo.ip[('way', 'src')]} route-map RM_UPLINK1_IN in\n")
    body.append(f"  neighbor {topo.ip[('alt', 'src')]} route-map RM_UPLINK2_IN in\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _upstream_config(topo: _Topo, role: str) -> str:
    """way or alt: eBGP to src and to dst, no policy, no statics."""
    p = topo.params
    eth = [("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name[role], topo.loopback[role], eth, [])
    body = [ib, _frr_header(topo.name[role]), fb]
    body.append(f"router bgp {p.asn[role]}\n")
    body.append(f" bgp router-id {topo.loopback[role]}\n")
    body.append(f" neighbor {topo.ip[('src', role)]} remote-as {p.asn['src']}\n")
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.asn['dst']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback[role]}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo) -> str:
    p = topo.params
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    ib, fb = _ifaces_intf_text(topo.name["dst"], topo.loopback["dst"], eth, dummies)
    body = [ib, _frr_header(topo.name["dst"]), fb]
    body.append(f"router bgp {p.asn['dst']}\n")
    body.append(f" bgp router-id {topo.loopback['dst']}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback['dst']}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _upstream_config(topo, "way"),
        topo.name["alt"]: _upstream_config(topo, "alt"),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change (an inbound-policy edit on src). One-line, idiomatic, no statics.
# --------------------------------------------------------------------------- #
def _apply_change(topo: _Topo) -> str:
    """Return the unified diff applied to src for this (knob, effect)."""
    knob, effect = topo.spec.knob, topo.spec.effect
    before = _src_config(topo)

    if knob == "lp_raise_alt":
        # bypass: raise the ALT inbound LP 100->300 (now beats way's 200).
        # no_op : raise the WAY inbound LP 200->300 (way was already preferred;
        #         widening its lead changes nothing).
        if effect == "bypass":
            old = ("route-map RM_UPLINK2_IN permit 10\n set local-preference 100\n")
            new = ("route-map RM_UPLINK2_IN permit 10\n set local-preference 300\n")
        else:
            old = ("route-map RM_UPLINK1_IN permit 10\n set local-preference 200\n")
            new = ("route-map RM_UPLINK1_IN permit 10\n set local-preference 300\n")
    elif knob == "lp_drop_way":
        # bypass: lower the WAY inbound LP 200->50 (now alt's 100 beats it).
        # no_op : lower the ALT inbound LP 100->50 (alt was already losing; making
        #         it lose harder changes nothing).
        if effect == "bypass":
            old = ("route-map RM_UPLINK1_IN permit 10\n set local-preference 200\n")
            new = ("route-map RM_UPLINK1_IN permit 10\n set local-preference 50\n")
        else:
            old = ("route-map RM_UPLINK2_IN permit 10\n set local-preference 100\n")
            new = ("route-map RM_UPLINK2_IN permit 10\n set local-preference 50\n")
    else:  # prepend_way
        # Equal LP; baseline already prepends alt once so way (shorter AS_PATH) wins.
        # All prepends use src's OWN ASN (literal-ASN syntax, Batfish-parseable).
        # bypass: add a prepend (x2) on the WAY inbound map -> way's AS_PATH becomes
        #         longer than alt's (x1) -> alt wins.
        # no_op : add MORE prepend on the ALT inbound map (alt's path was already
        #         longer/losing; lengthening it further changes nothing).
        a = topo.params.asn["src"]
        if effect == "bypass":
            old = ("route-map RM_UPLINK1_IN permit 10\n set local-preference 100\n!\n")
            new = ("route-map RM_UPLINK1_IN permit 10\n set local-preference 100\n"
                   f" set as-path prepend {a} {a}\n!\n")
        else:
            old = ("route-map RM_UPLINK2_IN permit 10\n set local-preference 100\n"
                   f" set as-path prepend {a}\n!\n")
            new = ("route-map RM_UPLINK2_IN permit 10\n set local-preference 100\n"
                   f" set as-path prepend {a} {a} {a}\n!\n")

    if old not in before:
        raise RuntimeError(
            f"change anchor not found for {topo.spec.dims_label()} on src "
            f"(seed render drift)"
        )
    after = before.replace(old, new, 1)
    return _unified(before, after, topo.name["src"])


def _unified(before: str, after: str, node: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"{node}.conf", tofile=f"{node}.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError(f"generated patch for {node} does not round-trip")
    return patch


# --------------------------------------------------------------------------- #
# Prose (CONFIG EDIT + INTENT ONLY — never the routing OUTCOME). The bypass and
# no_op variants are deliberately phrased the SAME way: the prose states only WHICH
# value on WHICH inbound map is edited, never whether the best path moves. This is
# the prompt-hygiene gate; "alt becomes preferred", "traffic bypasses", "nothing
# changes" are ALL leaks and appear NOWHERE.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    src = topo.name["src"]
    # Identify the edited construct WITHOUT revealing best-path consequences. We name
    # the route-map and the literal edit only; for no_op we name the OTHER map but in
    # the identical sentence shape so style cannot distinguish the two.
    if knob == "lp_raise_alt":
        which = "RM_UPLINK2_IN" if effect == "bypass" else "RM_UPLINK1_IN"
        frm = "100" if effect == "bypass" else "200"
        return (
            f"On `{src}` (AS{topo.params.asn['src']}), change the inbound eBGP "
            f"route-map `{which}` so its `set local-preference` value goes from "
            f"{frm} to 300 (a one-line value edit). See the diff."
        )
    if knob == "lp_drop_way":
        which = "RM_UPLINK1_IN" if effect == "bypass" else "RM_UPLINK2_IN"
        frm = "200" if effect == "bypass" else "100"
        return (
            f"On `{src}` (AS{topo.params.asn['src']}), change the inbound eBGP "
            f"route-map `{which}` so its `set local-preference` value goes from "
            f"{frm} to 50 (a one-line value edit). See the diff."
        )
    # prepend_way
    which = "RM_UPLINK1_IN" if effect == "bypass" else "RM_UPLINK2_IN"
    return (
        f"On `{src}` (AS{topo.params.asn['src']}), edit the inbound eBGP route-map "
        f"`{which}` to add/extend a `set as-path prepend` clause (an AS_PATH "
        f"adjustment). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tune inbound path preference for "
    "this destination."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: LpSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + all loopbacks (negative controls).
    watched = [f"{topo.loopback[r]}/32" for r in _ROLES] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host so
    # the trace has a real connected accept at dst (the bare .0 is not a host).
    waypoint_intents = [(src, cust_host, way)]

    name = f"gen_lp_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    scn = Scenario(
        name=name,
        nodes=[src, way, alt, dst],
        pre_configs=pre,
        change_target=src,
        patch=patch,
        description=description,
        intents_text=intents_text,
        watched_prefixes=watched,
        reachability_flows=reach,
        waypoint_intents=waypoint_intents,
        # bypass = the trap (consequential change, naive "session drops" is wrong);
        # no_op  = NOT a trap (the change is genuinely inert — empty GT). is_trap is
        # only meaningful when GT is non-empty, so no_op leaves it False.
        is_trap=(spec.effect == "bypass"),
        provenance="templated",
    )
    return scn


# --------------------------------------------------------------------------- #
# Public API (mirrors generator_ipc).
# --------------------------------------------------------------------------- #
def generate_lp_instance(seed: int, spec: Optional[LpSpec] = None) -> Scenario:
    """Emit ONE Class-5 instance.

    With ``spec=None`` the axis tuple is chosen deterministically from ``seed`` (so a
    bare ``generate_lp_instance(s)`` is reproducible and walks the space as ``s``
    varies). Passing an explicit ``spec`` pins the structure and uses ``seed`` only
    for the randomized addressing — how the suite enumerates every combo with
    distinct numbering.
    """
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[LpSpec]:
    """The enumerable spec list, optionally with the no_op (empty-GT) combos.

    ``include_noop`` (default True) gates the empty-ground-truth calibration combos.
    They grade cleanly end-to-end (a correct empty prediction scores macro_f1=1.0 /
    exact / pass — "correct by construction", which is intended; discrimination for
    no_op is via the model's false-positive / false_session_alarm rate, NOT vs the
    empty baseline). The grader's active-type rule means a CORRECTLY-handled no_op
    contributes to NO per-dimension cell (active_dims=[]), so it never distorts a
    per-dim mean; it influences only the macro_f1 / FSA-rate aggregates. The lead may
    set ``include_noop=False`` if a particular sweep wants the bypass-only macro, or
    may report no_op vs bypass macro separately — hence the explicit flag.
    """
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_lp_all_combos(*, seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """Emit exactly one instance per structural combo (6 with no_op, 3 without).

    Useful for the oracle round-trip / structural tests and for a minimal
    coverage-complete batch. Each combo gets a DISTINCT seed (``seed + position``)
    so addressing/naming also varies across the batch. See ``_selected_specs`` for
    the ``include_noop`` semantics.
    """
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_lp_suite(n: int, *, base_seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """Emit ``n`` DISTINCT Class-5 instances with unique ids.

    Coverage strategy (identical to generate_ipc_suite): walk the valid axis space
    in order, assigning each spec a distinct seed (``base_seed + position``) so the
    structure AND the randomized numbering both vary. If ``n`` exceeds the combo
    count we wrap with a fresh seed offset, giving the SAME structure a NEW
    randomized instance (still novel, still unique-id). Ids are guaranteed unique
    (the seed is in the name). ``include_noop`` (default True) gates the empty-GT
    calibration combos — see ``_selected_specs``.
    """
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        seed = base_seed + i
        out.append(_scenario_from_spec(spec, seed))
    return out
