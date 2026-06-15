"""Family-1 generator — INTER-AREA SUMMARY DISPLACEMENT (the `igp-summary-default-
nexthop` mechanism): an OSPF INTER-AREA (Type-3) summary metric change re-resolves an
UNCHANGED BGP next-hop across a DIFFERENT ABR, with ZERO BGP surface in the diff.

This is the third mechanism in the frozen quiet-half catalog (Family 1, BUILD_V1). It
is structurally DISTINCT from `igp-nh-metric-reroute` (the `generator_igp_metric`
sibling): that mechanism edits `ip ospf cost` on a TRANSIT LINK inside src's OWN area
(intra-area metric); THIS mechanism edits the metric of an INTER-AREA Type-3 SUMMARY
injected by an Area-Border-Router (a different abstraction layer — RFC 2328 §12.4.3
inter-area route computation, not the §16.1 intra-area SPF). The decisive change lives
at an ABR's backbone-facing interface and acts THROUGH the recursive next-hop
resolution of a BGP route whose every attribute AND best-path identity is byte-stable
across the diff.

Mechanism (RFC 4271 §9.1.2.2 step 6 — "prefer the path whose BGP NEXT_HOP is reachable
at lower IGP metric"; resolved here via an OSPF inter-area / Type-3 summary route): the
customer /24 is learned by `src` over iBGP from the egress `eg` with `eg`'s loopback as
the BGP NEXT_HOP (the Batfish-honored outbound route-map `set ip next-hop <eg-lo>` form
— NOT bare `next-hop-self`, a documented no-op on the pinned digest). `src` lives in a
non-backbone area and reaches `eg`'s loopback (in the backbone) only via a Type-3
summary injected by TWO Area-Border-Routers:

  * `wabr` — the ABR whose path transits the inspection WAYPOINT (`wabr` itself).
  * `babr` — the BYPASS ABR.

Each ABR injects a Type-3 summary of `eg`'s loopback into src's area; the metric of
that summary equals the ABR's intra-backbone OSPF cost to the loopback (RFC 2328
§12.4.3). `src`'s inter-area route to `eg-lo` is therefore (cost src->ABR in the
non-backbone area) + (that ABR's backbone cost to eg-lo), and the cheaper ABR wins.

  * PRE: the summary via `wabr` has STRICTLY lower cost, so `src` resolves eg-lo
    through `wabr` and src->customer transits the inspection node `wabr`.
  * DIFF: a single `ip ospf cost` line on ONE ABR's BACKBONE-facing interface — RAISE
    `wabr`'s backbone cost, or LOWER `babr`'s backbone cost — framed as a routine
    capacity/latency retune of the inter-area summary metric. (The classic operator
    knob for this is `area <N> range <prefix> cost <C>`; the pinned Batfish digest does
    NOT parse that override and silently ignores it, so the faithful, COMPUTABLE knob
    is the interface cost that DERIVES the very same Type-3 metric per RFC 2328
    §12.4.3. Verified 2026-06-14: `area range cost` is PARTIALLY_UNRECOGNIZED on the
    digest; the backbone-interface cost moves the OSPF_IA metric and is honored.)
  * POST: the inter-area summary metric to eg-lo is strictly lower via `babr`,
    best-path re-resolves through `babr`, and src->customer silently bypasses `wabr`.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): an OSPF cost change on an ABR
never resets the BGP FSM (RFC 4271 §8: Established exits only on NOTIFICATION/hold-
timer/TCP teardown) and is not an OSPF adjacency parameter, so D1=∅. The /24 stays
BEST and installed in every RIB (only the recursive resolution of its UNCHANGED
next-hop moves — the eg-lo /32 route is still present, its metric/exit-ABR just
changes), so D2=∅; `babr`'s path delivers exactly as `wabr`'s did (src->ABR->eg->dst,
ACCEPTED in both snapshots), so D3=∅, D7=∅. A STRICT (non-equal) inter-area metric gap
in BOTH snapshots means exactly one best path each time (maximum-paths default 1, no
equal-cost ECMP tie), so D5=∅ and the oracle is byte-identical. The strict gap also
means the decision is made at the IGP-metric step BEFORE the nondeterministic
router-id/age steps are reached (the documented Batfish ECMP-multipath trap), which is
what makes it deterministic AND keeps D5 empty.

PURITY GOTCHA (verified): the eg-lo /32 internal route must NOT DISAPPEAR (the summary
changes which-ABR / cost, never presence) or D2 would fire. The final discriminator is
the OSPF inter-area summary COST (a strict metric) — so it dodges the router-id trap.

Topology (5 nodes; multi-area OSPF underlay, iBGP overlay in one AS reflected by `eg`,
eBGP to the customer AS)::

        area 1 (non-backbone)            area 0 (backbone)
        +-- wabr (ABR, WAYPOINT) --+
        |                          |
      src                          eg --(eBGP /30)-- dst   customer /24
        |                          |                       (dual-attached host on dst)
        +-- babr (ABR, BYPASS) ----+
              ^ KNOB: `ip ospf cost` on an ABR's eg-facing (backbone) interface

  * src, wabr, babr, eg are ONE AS (iBGP; `eg` is the route-reflector, reflecting the
    customer /24 to src + both ABRs with the outbound `set ip next-hop <eg-lo>`). dst
    is a separate AS (eBGP), originating the customer /24 on a connected dummy host.
  * src<->wabr and src<->babr are OSPF point-to-point /30 links in AREA 1 (non-
    backbone). wabr<->eg and babr<->eg are OSPF /30 links in AREA 0 (backbone). Each
    ABR is therefore area-1 on its src side and area-0 on its eg side (true ABR).
  * eg<->dst is the eBGP /30 link and is NOT in OSPF.
  * src applies NO BGP policy; it has exactly one received path to the customer (from
    eg). The change edits ONE `ip ospf cost` value on an ABR's backbone interface —
    zero BGP-namespace surface.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {raise_wabr, lower_babr} — two DIFFERENT inter-area-metric edits that both
    flip the egress off the waypoint, each on a DIFFERENT ABR / opposite direction:
      - raise_wabr : baseline backbone cost(wabr)=10 < cost(babr)=100 (wabr summary
        wins). The change RAISES `wabr`'s backbone cost to 200, so babr's summary now
        wins (110 < 210). change_target = wabr.
      - lower_babr : same baseline. The change LOWERS `babr`'s backbone cost to 5, so
        babr's summary now wins (15 < 20). change_target = babr. Same outcome,
        opposite edit, a different ABR to read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually flips the recursive resolution. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of backbone-interface `ip ospf cost` edit applied where
        it does NOT change the winner (raise the already-LOSING babr summary higher;
        lower the already-WINNING wabr summary lower). Ground truth is COMPLETELY
        EMPTY across ALL dimensions — the calibration trap (the model must predict an
        empty blast radius). The prose is indistinguishable in style from a bypass edit.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_igp_metric): the
core ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer
/24, the non-backbone area id, and the node base name are all drawn deterministically
from the seed.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path
decision is STRICT at the inter-area-metric step in both snapshots (a real, non-equal
OSPF cost gap) — exactly one best path at src in each snapshot, no equal-cost ECMP tie,
maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

Live-verified (2026-06-14, pinned batfish/allinone:nethelm, network
"netbrace_build_igp_summary"):
  * raise_wabr/bypass -> D4 waypoint + D10 intent ONLY (D1/D2/D3/D5/D7=∅); reachability
    survives via babr (src->babr->eg->dst ACCEPTED).
  * lower_babr/bypass -> D4 + D10 ONLY.
  * *_no_op           -> COMPLETELY EMPTY across all dims.
  * both bypass combos 10x byte-identical (determinism gate).

Public API mirrors generator_igp_metric:
    generate_igp_summary_suite(n, base_seed=...)        -> list[Scenario]
    generate_igp_summary_all_combos(seed=...)           -> list[Scenario]
    generate_igp_summary_instance(seed, spec=None)      -> Scenario
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
KNOB_VALUES = ("raise_wabr", "lower_babr")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# Baseline OSPF backbone-interface costs on the two ABRs (the Type-3 summary metric
# input). wabr's summary strictly cheaper PRE so src resolves eg-lo via wabr.
_COST_WABR_PRE = 10
_COST_BABR_PRE = 100
# Post values (chosen to keep a STRICT inter-area metric gap in the post snapshot too;
# the inter-area metric at src = src->ABR area-1 cost (1) + ABR backbone cost).
_COST_WABR_RAISED = 200   # raise_wabr/bypass: 200 > 100 -> babr summary wins
_COST_BABR_LOWERED = 5    # lower_babr/bypass: 5 < 10   -> babr summary wins
_COST_BABR_RAISED = 300   # raise_wabr/no_op: 100->300, wabr (10) still wins (inert)
_COST_WABR_LOWERED = 5    # lower_babr/no_op: 10->5,   wabr still wins (inert)

# Fixed area-1-side interface cost on each ABR (kept equal + cheap so the discriminator
# lives entirely in the backbone summary metric, never in the src-side link).
_AREA1_LINK_COST = 1


@dataclass(frozen=True)
class IgpSummarySpec:
    """A point in the Family-1 igp-summary generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[IgpSummarySpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[IgpSummarySpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(IgpSummarySpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the core (src/wabr/babr/eg
# share one AS -> iBGP) and the customer AS (dst). Clear of the hand-authored 65000
# family.
_ASN_LO, _ASN_HI = 4_200_300_000, 4_200_399_999

_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]

# Topology roles, in a FIXED order (used for loopback indexing + the node list base).
_ROLES = ("src", "wabr", "babr", "eg", "dst")


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    core_asn: int            # src/wabr/babr/eg share this (iBGP)
    dst_asn: int             # the customer AS (eBGP)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    area1: int               # the non-backbone area id (src side); backbone is 0
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

    area1 = rng.randint(1, 4094)  # any valid non-backbone area id

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    return _Params(core_asn=core_asn, dst_asn=dst_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, area1=area1,
                   name=name)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first):
#   src-wabr (area1), src-babr (area1), wabr-eg (area0), babr-eg (area0), eg-dst (eBGP).
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: IgpSummarySpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str
    area1: int


def _build_topo(spec: IgpSummarySpec, params: _Params) -> _Topo:
    name = dict(params.name)
    rid_index = {"src": 1, "wabr": 2, "babr": 3, "eg": 4, "dst": 5}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved from the link block:
    #   src-wabr  base .0  (src=.1,  wabr=.2)   OSPF area1
    #   src-babr  base .4  (src=.5,  babr=.6)   OSPF area1
    #   wabr-eg   base .8  (wabr=.9, eg=.10)    OSPF area0
    #   babr-eg   base .12 (babr=.13, eg=.14)   OSPF area0
    #   eg-dst    base .16 (eg=.17,  dst=.18)   eBGP (no OSPF)
    ip: dict[tuple[str, str], str] = {
        ("src", "wabr"): addr(1), ("wabr", "src"): addr(2),
        ("src", "babr"): addr(5), ("babr", "src"): addr(6),
        ("wabr", "eg"): addr(9), ("eg", "wabr"): addr(10),
        ("babr", "eg"): addr(13), ("eg", "babr"): addr(14),
        ("eg", "dst"): addr(17), ("dst", "eg"): addr(18),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip,
                 area1=params.area1)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 format). Multi-area OSPF: src-side links in the non-backbone
# area, eg-side links + every backbone loopback in area 0; iBGP over loopbacks (eg is
# the reflector); egress next-hop rewrite via outbound route-map. NO static routes.
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


def _ospf_iface(iface: str, ipm: str, area: int, cost: Optional[int] = None) -> str:
    lines = [f"interface {iface}", f" ip address {ipm}",
             f" ip ospf area {area}", " ip ospf network point-to-point"]
    if cost is not None:
        lines.append(f" ip ospf cost {cost}")
    lines.append("!")
    return "\n".join(lines) + "\n"


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


def _src_config(topo: _Topo) -> str:
    """src: OSPF (area1) to both ABRs, iBGP to eg (the reflector). NO BGP policy. It
    has exactly one received path to the customer (from eg), resolved recursively via
    whichever ABR's inter-area summary to eg-lo is cheaper."""
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'wabr')]}/30"),
           ("eth2", f"{topo.ip[('src', 'babr')]}/30")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area {topo.area1}\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('src', 'wabr')]}/30", topo.area1))
    body.append(_ospf_iface("eth2", f"{topo.ip[('src', 'babr')]}/30", topo.area1))
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.loopback['eg']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['eg']} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _abr_config(topo: _Topo, role: str, backbone_cost: int) -> str:
    """wabr or babr: an ABR. eth1 (area1) toward src, eth2 (area0, the KNOB cost)
    toward eg. iBGP client of the reflector eg (so it learns + forwards the customer
    /24 with eg-lo as next-hop, resolved via its own area-0 route to eg-lo). The
    `backbone_cost` on eth2 is the input to the Type-3 summary metric eg-lo gets into
    src's area (RFC 2328 §12.4.3) — the metric-bearing line this mechanism edits."""
    p = topo.params
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'src')]}/30"),
           ("eth2", f"{topo.ip[(role, 'eg')]}/30")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    # area1 toward src (cheap, fixed); area0 toward eg carries the summary-metric KNOB.
    body.append(_ospf_iface("eth1", f"{topo.ip[(role, 'src')]}/30", topo.area1,
                            cost=_AREA1_LINK_COST))
    body.append(_ospf_iface("eth2", f"{topo.ip[(role, 'eg')]}/30", 0,
                            cost=backbone_cost))
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.loopback['eg']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['eg']} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _eg_config(topo: _Topo) -> str:
    """eg: the iBGP route-reflector + the egress. OSPF (area0) to both ABRs, eBGP to
    dst (no OSPF), iBGP to src + both ABRs as RR clients with an OUTBOUND `set ip
    next-hop <own-lo>` (the Batfish-honored next-hop-self form). Re-advertises dst's
    customer /24 to the core with eg-lo as the recursive next-hop."""
    p = topo.params
    lo = topo.loopback["eg"]
    eth = [("eth1", f"{topo.ip[('eg', 'wabr')]}/30"),
           ("eth2", f"{topo.ip[('eg', 'babr')]}/30"),
           ("eth3", f"{topo.ip[('eg', 'dst')]}/30")]
    body = [_iface_header(topo.name["eg"], lo, eth, []), _frr_header(topo.name["eg"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('eg', 'wabr')]}/30", 0))
    body.append(_ospf_iface("eth2", f"{topo.ip[('eg', 'babr')]}/30", 0))
    body.append(_plain_iface("eth3", f"{topo.ip[('eg', 'dst')]}/30"))  # eBGP, no OSPF
    body.append(f"route-map NHS_OUT permit 10\n set ip next-hop {lo}\n!\n")
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    for client in ("src", "wabr", "babr"):
        body.append(f" neighbor {topo.loopback[client]} remote-as {p.core_asn}\n")
        body.append(f" neighbor {topo.loopback[client]} update-source lo\n")
    body.append(f" neighbor {topo.ip[('dst', 'eg')]} remote-as {p.dst_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    for client in ("src", "wabr", "babr"):
        body.append(f"  neighbor {topo.loopback[client]} route-reflector-client\n")
        body.append(f"  neighbor {topo.loopback[client]} route-map NHS_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo) -> str:
    """dst: the customer AS, eBGP to eg, originates the customer /24 + its lo."""
    p = topo.params
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'eg')]}/30")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["dst"], lo, eth, dummies),
            _frr_header(topo.name["dst"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', 'eg')]}/30"))
    body.append(f"interface dum0\n ip address {topo.customer_ip}/24\n!\n")
    body.append(f"router bgp {p.dst_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('eg', 'dst')]} remote-as {p.core_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["wabr"]: _abr_config(topo, "wabr", _COST_WABR_PRE),
        topo.name["babr"]: _abr_config(topo, "babr", _COST_BABR_PRE),
        topo.name["eg"]: _eg_config(topo),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# Which ABR each combo edits, and the before/after backbone cost on it. Zero
# BGP-namespace surface (a single `ip ospf cost` line on the ABR's eth2/backbone).
# --------------------------------------------------------------------------- #
def _change_plan(spec: IgpSummarySpec) -> tuple[str, int, int]:
    """Return (abr_role_to_edit, before_cost, after_cost) for the spec.

    raise_wabr/bypass : edit wabr  10 -> 200  (babr summary now wins -> bypass)
    raise_wabr/no_op  : edit babr (already losing) 100 -> 300 (wabr still wins, inert)
    lower_babr/bypass : edit babr 100 -> 5    (babr summary now wins -> bypass)
    lower_babr/no_op  : edit wabr (already winning) 10 -> 5  (wabr still wins, inert)
    """
    knob, effect = spec.knob, spec.effect
    if knob == "raise_wabr":
        if effect == "bypass":
            return "wabr", _COST_WABR_PRE, _COST_WABR_RAISED
        return "babr", _COST_BABR_PRE, _COST_BABR_RAISED
    else:  # lower_babr
        if effect == "bypass":
            return "babr", _COST_BABR_PRE, _COST_BABR_LOWERED
        return "wabr", _COST_WABR_PRE, _COST_WABR_LOWERED


def _apply_change(topo: _Topo) -> tuple[str, str]:
    """Build the unified diff for the one `ip ospf cost` edit. Returns
    (changed_node_name, patch)."""
    abr_role, before_cost, after_cost = _change_plan(topo.spec)
    node_name = topo.name[abr_role]
    before = _abr_config(topo, abr_role, before_cost)
    after = _abr_config(topo, abr_role, after_cost)

    old = f" ip ospf cost {before_cost}\n"
    new = f" ip ospf cost {after_cost}\n"
    # The edited backbone cost line is the eth2 cost; eth1 carries the fixed area-1
    # cost (_AREA1_LINK_COST=1), which never equals the backbone costs, so the swap
    # is unambiguous.
    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {topo.spec.dims_label()} on "
            f"{abr_role} (seed render drift)"
        )
    if before.replace(old, new, 1) != after:
        raise RuntimeError(
            f"change for {topo.spec.dims_label()} is not a single-line cost swap"
        )
    return node_name, _unified(before, after, node_name)


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
# phrased the SAME way: the prose names only WHICH ABR's backbone-facing OSPF cost is
# edited and the value, never whether the recursive resolution / best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    abr_role, before_cost, after_cost = _change_plan(topo.spec)
    node = topo.name[abr_role]
    # eth2 is always the backbone (eg-facing) interface on an ABR.
    return (
        f"On `{node}` (AS{topo.params.core_asn}), change the OSPF interface cost on "
        f"`eth2` (its backbone-area link toward the egress) from {before_cost} to "
        f"{after_cost} (a one-line `ip ospf cost` edit on the inter-area summary's "
        f"metric input). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to retune the inter-area summary "
    "metric for this path."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: IgpSummarySpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    change_node, patch = _apply_change(topo)

    src = topo.name["src"]
    wabr = topo.name["wabr"]   # the WAYPOINT (inspection node)
    babr = topo.name["babr"]
    eg = topo.name["eg"]
    dst = topo.name["dst"]
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the four core loopbacks (negative controls). The
    # eg-lo is the recursively-resolved next-hop and is the critical negative control:
    # it must STAY present (only its resolving ABR/metric moves) or D2 would fire.
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "wabr", "babr", "eg")] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path via babr).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `wabr`. Probe the /32 host.
    waypoint_intents = [(src, cust_host, wabr)]

    # D10 intent invariant: the SAME waypoint, restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=wabr,
            note=f"igp-summary quiet reroute: src->{cust} must transit {wabr}",
        )
    ]

    # Node list: the EDITED ABR first (change_target == nodes[0]), then the rest in a
    # fixed topology order. The waypoint is always `wabr` (exposed via waypoint_intents
    # / intent_invariants, not by node position, since the edited ABR varies by combo).
    rest = [n for n in (src, wabr, babr, eg, dst) if n != change_node]
    nodes = [change_node] + rest

    name = f"gen_igp_summary_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=wabr)

    return Scenario(
        name=name,
        nodes=nodes,
        pre_configs=pre,
        change_target=change_node,
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
# Public API (mirrors generator_igp_metric).
# --------------------------------------------------------------------------- #
def generate_igp_summary_instance(seed: int, spec: Optional[IgpSummarySpec] = None) -> Scenario:
    """Emit ONE Family-1 igp-summary instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[IgpSummarySpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_igp_summary_all_combos(*, seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_igp_summary_suite(n: int, *, base_seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct
    seed per position; wrap with a fresh seed offset when ``n`` exceeds the combo
    count, giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
