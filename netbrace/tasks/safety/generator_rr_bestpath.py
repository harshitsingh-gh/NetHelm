r"""Family-3 generator — RR-SINGLE-BEST-PATH PROJECTION (the `rr-bestpath-reflect-flip`
mechanism): a route-reflector reflects only its ONE best path (RFC 4456 §11), so an
edit that flips the REFLECTOR's own best egress silently re-homes a downstream client
that never had a choice of its own — with ZERO BGP surface in the diff.

This is a Family-3 (projection) mechanism in the frozen quiet-half catalog (BUILD_V1).
It is structurally DISTINCT from the Family-1 `igp-nh-metric-reroute` /
`igp-summary-default-nexthop` siblings: in those, the VICTIM node (`src`) itself holds
two attribute-tied paths and resolves the winner through its own IGP metric. HERE the
victim `src` holds exactly ONE path — it is an RR client that learns the customer /24
ONLY from the reflector `rr` (no second reflector, no add-path), so `src` forwards on
whatever SINGLE path `rr` chose and has no local decision to make. The decisive flip
lives at the REFLECTOR and PROJECTS down onto `src`. RFC 4456 §11 is explicit: a
reflector advertises only its best path to its clients; a client therefore inherits the
reflector's egress selection wholesale.

Mechanism (RFC 4456 §11 best-path reflection + RFC 4271 §9.1.2.2 step 6 IGP-metric
tiebreak): `rr` learns the customer /24 over iBGP from BOTH egresses `way` and `alt`
with BYTE-IDENTICAL BGP attributes (same LOCAL_PREF, same AS_PATH = [AS_dst], same
ORIGIN, same MED, both iBGP). No BGP attribute can decide, so `rr`'s best-path falls
through to the IGP-metric tiebreak, resolving each path's NEXT_HOP (the advertising
egress's loopback, set via the Batfish-honored outbound route-map `set ip next-hop
<lo>` — NOT bare `next-hop-self`, a documented no-op on the pinned digest for
eBGP-learned routes) recursively through the OSPF RIB. `rr` then reflects its ONE
chosen path to `src`.

  * PRE: OSPF cost rr->way-lo is STRICTLY lower than rr->alt-lo, so `rr`'s own best is
    the `way` egress; `rr` reflects the `way` path to `src`, and src->customer transits
    the inspection node `way`.
  * DIFF (bypass): a single `ip ospf cost` line on ONE of `rr`'s underlay interfaces —
    RAISE `rr`'s cost toward `way`, or LOWER `rr`'s cost toward `alt` — framed as a
    routine capacity/latency retune. ZERO BGP-namespace surface.
  * POST: the IGP metric rr->alt-lo is strictly lower, `rr`'s own best re-resolves to
    the `alt` egress, `rr` reflects the `alt` path to `src`, and src->customer silently
    bypasses `way`. `src`'s diff is EMPTY — it never changed; it just inherits the
    reflector's new single best path.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): an OSPF cost change never resets
the BGP FSM (RFC 4271 §8: Established exits only on NOTIFICATION/hold-timer/TCP
teardown) and is not an OSPF adjacency parameter, so D1=∅. The /24 stays BEST and
installed in every RIB (only the reflected path's resolved egress moves — `src` still
has exactly one installed best path before and after), so D2=∅; `alt` delivers exactly
as `way` did, so D3=∅, D7=∅. Because `rr` reflects only ONE best path and `src` learns
ONLY from `rr`, `src` has exactly ONE installed path in BOTH snapshots — installed-path
count 1->1, so D5=∅. A STRICT (non-equal) IGP cost gap at `rr` in BOTH snapshots means
`rr` has exactly one best path each time (no equal-cost ECMP tie at the reflector
either), so the oracle is byte-identical. The strict gap also means the decision is
made at the IGP-metric step BEFORE the nondeterministic router-id/age steps are reached
(the documented Batfish ECMP-multipath trap), which keeps the choice deterministic AND
keeps D5 empty at every node.

PURITY GOTCHA (verified design): `src` MUST learn the /24 only from `rr` (single
reflector, no add-path) so it has one path, not two — otherwise `src` would itself hold
the way/alt choice and the mechanism would collapse into the Family-1 igp-metric one
(and could fire D5 if the two paths ever tied). The way-lo and alt-lo /32 internal
routes must BOTH remain present in every RIB (the flip changes WHICH egress `rr`
reflects, never the presence of either loopback) or D2 would fire.

Topology (5 nodes; OSPF underlay among src/rr/way/alt, iBGP overlay in one AS with `rr`
as the sole route-reflector, eBGP from each egress to the customer AS)::

                 way --(eBGP /30)-- dst   customer /24
                /                   /     (originated by dst AS_dst,
       src --- rr                  /       dual-homed eBGP to way & alt)
                \                  /
                 alt --(eBGP /30)-+
              ^ KNOB: `ip ospf cost` on rr's underlay interface toward way / toward alt

  * src, rr, way, alt are ONE AS (iBGP, OSPF speakers). dst is a separate AS (eBGP),
    originating the customer /24 on a connected dummy host.
  * rr<->way and rr<->alt are OSPF point-to-point /30 links (the metric-bearing links;
    their cost is the tiebreak input at rr). src<->rr is an OSPF /30 link (cheap,
    fixed; never the discriminator). way<->dst and alt<->dst are eBGP /30 links and are
    NOT in OSPF.
  * `rr` is the iBGP route-reflector; src, way, alt are its clients. `src` peers ONLY
    `rr` (one path). way/alt re-advertise dst's customer /24 to `rr` over iBGP with an
    outbound `set ip next-hop <own-lo>`; `rr` reflects its single best to `src` with an
    outbound `set ip next-hop <chosen-egress-lo>` PASS-THROUGH (it reflects the path's
    NEXT_HOP unchanged — clients resolve the egress loopback via OSPF).
  * No node applies any BGP best-path policy on the customer /24; the two paths `rr`
    receives are attribute-tied. The change edits ONE `ip ospf cost` value on `rr` —
    zero BGP-namespace surface.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {raise_way, lower_alt} — two DIFFERENT OSPF cost edits on `rr` that both
    flip the reflected egress off the waypoint, each on a different rr interface /
    opposite direction:
      - raise_way : baseline cost(rr->way)=10 < cost(rr->alt)=100 (way wins at rr); the
        change RAISES rr's cost toward way to 200, so alt now wins (100 < 200).
      - lower_alt : same baseline; the change LOWERS rr's cost toward alt to 5, so alt
        now wins (5 < 10). Same outcome, opposite edit, different rr interface to read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually flips rr's single best (and thus the reflected path).
        D4+D10 fire; D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of `ip ospf cost` edit applied where it does NOT change
        rr's winner (raise the already-LOSING alt-side cost higher; lower the
        already-WINNING way-side cost lower). Ground truth is COMPLETELY EMPTY across
        ALL dimensions — the calibration trap (the model must predict an empty blast
        radius). The prose is indistinguishable in style from a bypass edit.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_igp_summary): the
core ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer
/24, and the node base name are all drawn deterministically from the seed.

Determinism contract (oracle_determinism_spec class STATIC-DET): `rr`'s best-path
decision is STRICT at the IGP-metric step in both snapshots (a real, non-equal OSPF
cost gap rr->way-lo vs rr->alt-lo) — exactly one best path at `rr` in each snapshot,
reflected as exactly one installed path at `src`, no equal-cost ECMP tie anywhere,
maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

Public API mirrors generator_igp_summary:
    generate_rr_bestpath_suite(n, base_seed=...)        -> list[Scenario]
    generate_rr_bestpath_all_combos(seed=...)           -> list[Scenario]
    generate_rr_bestpath_instance(seed, spec=None)      -> Scenario
    enumerate_specs() / enumerable_count()
"""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass
from typing import Optional

from netbrace.tasks.safety.scenarios import IntentInvariant, Scenario
from netbrace.topology.patches import apply_unified_diff

# --------------------------------------------------------------------------- #
# Axis value sets (the enumerable space).
# --------------------------------------------------------------------------- #
KNOB_VALUES = ("raise_way", "lower_alt")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# Baseline OSPF costs on rr's two egress-facing underlay interfaces. way strictly
# cheaper PRE so rr's single best (and the reflected path) is the way egress.
_COST_WAY_PRE = 10
_COST_ALT_PRE = 100
# Post values (chosen to keep a STRICT gap in the post snapshot too).
_COST_WAY_RAISED = 200   # raise_way/bypass: 200 > 100 -> alt wins at rr
_COST_ALT_LOWERED = 5    # lower_alt/bypass: 5 < 10  -> alt wins at rr
_COST_ALT_RAISED = 300   # raise_way/no_op: 100->300, way (10) still wins (inert)
_COST_WAY_LOWERED = 5    # lower_alt/no_op: 10->5,  way still wins (inert)

# src<->rr underlay cost: cheap + fixed, never the discriminator. (Distinct from any
# egress cost value so a cost-line swap on rr's egress interface is unambiguous.)
_SRC_LINK_COST = 1


@dataclass(frozen=True)
class RrBestpathSpec:
    """A point in the Family-3 rr-bestpath generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[RrBestpathSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[RrBestpathSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(RrBestpathSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the core (src/rr/way/alt
# share one AS -> iBGP) and the customer AS (dst). Clear of the hand-authored 65000
# family AND of the other generators' sub-ranges.
_ASN_LO, _ASN_HI = 4_200_400_000, 4_200_499_999

_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]

# Topology roles, in a FIXED order (used for loopback indexing + the node list base).
_ROLES = ("src", "rr", "way", "alt", "dst")


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    core_asn: int            # src/rr/way/alt share this (iBGP)
    dst_asn: int             # the customer AS (eBGP)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    core_asn = rng.randint(_ASN_LO, _ASN_HI)
    dst_asn = core_asn
    while dst_asn == core_asn:
        dst_asn = rng.randint(_ASN_LO, _ASN_HI)

    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    return _Params(core_asn=core_asn, dst_asn=dst_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, name=name)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first):
#   src-rr (OSPF), rr-way (OSPF, KNOB), rr-alt (OSPF, KNOB),
#   way-dst (eBGP), alt-dst (eBGP).
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: RrBestpathSpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: RrBestpathSpec, params: _Params) -> _Topo:
    name = dict(params.name)
    rid_index = {"src": 1, "rr": 2, "way": 3, "alt": 4, "dst": 5}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved from the link block:
    #   src-rr   base .0  (src=.1,  rr=.2)    OSPF
    #   rr-way   base .4  (rr=.5,   way=.6)   OSPF (rr-side cost is the KNOB)
    #   rr-alt   base .8  (rr=.9,   alt=.10)  OSPF (rr-side cost is the KNOB)
    #   way-dst  base .12 (way=.13, dst=.14)  eBGP (no OSPF)
    #   alt-dst  base .16 (alt=.17, dst=.18)  eBGP (no OSPF)
    ip: dict[tuple[str, str], str] = {
        ("src", "rr"): addr(1), ("rr", "src"): addr(2),
        ("rr", "way"): addr(5), ("way", "rr"): addr(6),
        ("rr", "alt"): addr(9), ("alt", "rr"): addr(10),
        ("way", "dst"): addr(13), ("dst", "way"): addr(14),
        ("alt", "dst"): addr(17), ("dst", "alt"): addr(18),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 format). OSPF underlay among src/rr/way/alt; eBGP /30s are NOT
# in OSPF; iBGP over loopbacks (rr is the reflector); egress next-hop rewrite via
# outbound route-map. NO static routes.
# --------------------------------------------------------------------------- #
_FRR_VER = "frr version 10.6.1"


def _iface_header(node_name: str, loopback: str,
                  eth: list[tuple[str, str]], dummies: list[tuple[str, str]]) -> str:
    """The /etc/network/interfaces-style block (CUMULUS_CONCATENATED header)."""
    ib = [
        node_name, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {loopback}/32", "",
    ]
    for iface, ipm in eth + dummies:
        ib += [f"auto {iface}", f"iface {iface} inet static", f"    address {ipm}", ""]
    ib += ["# ports.conf --", ""]
    return "\n".join(ib) + "\n"


def _frr_header(node_name: str) -> str:
    return (
        f"{_FRR_VER}\n"
        "frr defaults traditional\n"
        f"hostname {node_name}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


def _ospf_iface(iface: str, ipm: str, cost: Optional[int] = None) -> str:
    lines = [f"interface {iface}", f" ip address {ipm}",
             " ip ospf area 0", " ip ospf network point-to-point"]
    if cost is not None:
        lines.append(f" ip ospf cost {cost}")
    lines.append("!")
    return "\n".join(lines) + "\n"


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


def _src_config(topo: _Topo) -> str:
    """src: an RR client. OSPF (area0) to rr only, iBGP to rr ONLY (single reflector,
    one received path). NO BGP policy. It inherits whatever single best path rr
    reflects, resolving the reflected egress loopback recursively via OSPF."""
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'rr')]}/30")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('src', 'rr')]}/30", cost=_SRC_LINK_COST))
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.loopback['rr']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['rr']} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _rr_config(topo: _Topo, *, cost_way: int, cost_alt: int) -> str:
    """rr: the iBGP route-reflector + the IGP-tiebreak node. OSPF (area0) to src, way,
    alt — the way/alt interface costs (the KNOB) decide rr's single best egress. iBGP
    RR for src, way, alt over loopbacks. way/alt re-advertise the customer /24 to rr
    with their own loopback as NEXT_HOP; rr reflects its ONE best to src with the
    path's NEXT_HOP passed through (NHS_OUT pass-through `set ip next-hop` toward src is
    NOT applied — rr keeps the egress loopback so src resolves it recursively)."""
    p = topo.params
    lo = topo.loopback["rr"]
    eth = [("eth1", f"{topo.ip[('rr', 'src')]}/30"),
           ("eth2", f"{topo.ip[('rr', 'way')]}/30"),
           ("eth3", f"{topo.ip[('rr', 'alt')]}/30")]
    body = [_iface_header(topo.name["rr"], lo, eth, []), _frr_header(topo.name["rr"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('rr', 'src')]}/30", cost=_SRC_LINK_COST))
    body.append(_ospf_iface("eth2", f"{topo.ip[('rr', 'way')]}/30", cost=cost_way))
    body.append(_ospf_iface("eth3", f"{topo.ip[('rr', 'alt')]}/30", cost=cost_alt))
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    for client in ("src", "way", "alt"):
        body.append(f" neighbor {topo.loopback[client]} remote-as {p.core_asn}\n")
        body.append(f" neighbor {topo.loopback[client]} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    for client in ("src", "way", "alt"):
        body.append(f"  neighbor {topo.loopback[client]} route-reflector-client\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _egress_config(topo: _Topo, role: str) -> str:
    """way or alt: OSPF to rr (metric link), eBGP to dst (no OSPF), iBGP to rr with an
    OUTBOUND `set ip next-hop <own-lo>` toward rr (the Batfish-honored next-hop-self
    form). Re-advertises dst's customer /24 to rr; rr's two received copies are
    attribute-tied, so rr's choice falls to its OSPF metric to each egress loopback."""
    p = topo.params
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'rr')]}/30"),
           ("eth2", f"{topo.ip[(role, 'dst')]}/30")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[(role, 'rr')]}/30"))     # OSPF underlay
    body.append(_plain_iface("eth2", f"{topo.ip[(role, 'dst')]}/30"))   # eBGP, no OSPF
    body.append(f"route-map NHS_OUT permit 10\n set ip next-hop {lo}\n!\n")
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    # iBGP to rr (next-hop-self via route-map).
    body.append(f" neighbor {topo.loopback['rr']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['rr']} update-source lo\n")
    # eBGP to dst (directly-connected link IP).
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.dst_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  neighbor {topo.loopback['rr']} route-map NHS_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo) -> str:
    """dst: the customer AS, eBGP to way + alt, originates the customer /24 + its lo."""
    p = topo.params
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}/30"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}/30")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["dst"], lo, eth, dummies),
            _frr_header(topo.name["dst"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', 'way')]}/30"))
    body.append(_plain_iface("eth2", f"{topo.ip[('dst', 'alt')]}/30"))
    body.append(f"interface dum0\n ip address {topo.customer_ip}/24\n!\n")
    body.append(f"router bgp {p.dst_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.core_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["rr"]: _rr_config(topo, cost_way=_COST_WAY_PRE, cost_alt=_COST_ALT_PRE),
        topo.name["way"]: _egress_config(topo, "way"),
        topo.name["alt"]: _egress_config(topo, "alt"),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change: a single `ip ospf cost` edit on rr's egress-facing interface. Zero
# BGP-namespace surface. eth2 = rr->way, eth3 = rr->alt.
# --------------------------------------------------------------------------- #
def _change_plan(spec: RrBestpathSpec) -> tuple[str, int, int]:
    """Return (rr_iface_to_edit, before_cost, after_cost) for the spec.

    raise_way/bypass : edit eth2 (rr->way) 10 -> 200  (alt now wins at rr -> bypass)
    raise_way/no_op  : edit eth3 (rr->alt, already losing) 100 -> 300 (way still wins)
    lower_alt/bypass : edit eth3 (rr->alt) 100 -> 5   (alt now wins at rr -> bypass)
    lower_alt/no_op  : edit eth2 (rr->way, already winning) 10 -> 5  (way still wins)
    """
    knob, effect = spec.knob, spec.effect
    if knob == "raise_way":
        if effect == "bypass":
            return "eth2", _COST_WAY_PRE, _COST_WAY_RAISED
        return "eth3", _COST_ALT_PRE, _COST_ALT_RAISED
    else:  # lower_alt
        if effect == "bypass":
            return "eth3", _COST_ALT_PRE, _COST_ALT_LOWERED
        return "eth2", _COST_WAY_PRE, _COST_WAY_LOWERED


def _apply_change(topo: _Topo) -> str:
    """Build the unified diff for the one `ip ospf cost` edit on rr. The edited line is
    on the egress-facing interface (eth2/eth3); eth1 carries the fixed _SRC_LINK_COST
    which never equals any egress cost, so the swap is unambiguous."""
    iface, before_cost, after_cost = _change_plan(topo.spec)

    if iface == "eth2":  # rr->way
        before = _rr_config(topo, cost_way=before_cost, cost_alt=_COST_ALT_PRE)
        after = _rr_config(topo, cost_way=after_cost, cost_alt=_COST_ALT_PRE)
    else:  # eth3, rr->alt
        before = _rr_config(topo, cost_way=_COST_WAY_PRE, cost_alt=before_cost)
        after = _rr_config(topo, cost_way=_COST_WAY_PRE, cost_alt=after_cost)

    old = f" ip ospf cost {before_cost}\n"
    new = f" ip ospf cost {after_cost}\n"
    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {topo.spec.dims_label()} on rr "
            f"(seed render drift)"
        )
    if before.replace(old, new, 1) != after:
        raise RuntimeError(
            f"change for {topo.spec.dims_label()} is not a single-line cost swap"
        )
    return _unified(before, after, topo.name["rr"])


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
# Prose (CONFIG EDIT + INTENT ONLY — never the routing OUTCOME). bypass and no_op are
# phrased the SAME way: the prose names only WHICH rr interface's OSPF cost is edited
# and the value, never whether rr's reflected best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    iface, before_cost, after_cost = _change_plan(topo.spec)
    rr = topo.name["rr"]
    return (
        f"On `{rr}` (AS{topo.params.core_asn}), change the OSPF interface cost on "
        f"`{iface}` from {before_cost} to {after_cost} (a one-line `ip ospf cost` "
        f"edit). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to retune interior link metrics for "
    "this path."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: RrBestpathSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src = topo.name["src"]
    rr = topo.name["rr"]
    way = topo.name["way"]     # the WAYPOINT (inspection egress)
    alt = topo.name["alt"]
    dst = topo.name["dst"]
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the four core loopbacks (negative controls). way-lo
    # and alt-lo are the recursively-resolved egress next-hops and are critical
    # negative controls: BOTH must STAY present (only which one rr reflects moves) or
    # D2 would fire.
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "rr", "way", "alt")] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path via alt).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host.
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint, restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"rr-bestpath quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_rr_bestpath_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    return Scenario(
        name=name,
        nodes=[rr, src, way, alt, dst],  # change_target (rr) first
        pre_configs=pre,
        change_target=rr,
        patch=patch,
        description=description,
        intents_text=intents_text,
        watched_prefixes=watched,
        reachability_flows=reach,
        waypoint_intents=waypoint_intents,
        intent_invariants=intent_invariants,
        # bypass = the trap (D4+D10 fire while sessions/prefixes/reachability survive);
        # no_op  = genuinely inert (empty GT), so is_trap stays False.
        is_trap=(spec.effect == "bypass"),
        provenance="templated",
    )


# --------------------------------------------------------------------------- #
# Public API (mirrors generator_igp_summary).
# --------------------------------------------------------------------------- #
def generate_rr_bestpath_instance(seed: int, spec: Optional[RrBestpathSpec] = None) -> Scenario:
    """Emit ONE Family-3 rr-bestpath instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[RrBestpathSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_rr_bestpath_all_combos(*, seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_rr_bestpath_suite(n: int, *, base_seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct
    seed per position; wrap with a fresh seed offset when ``n`` exceeds the combo
    count, giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
