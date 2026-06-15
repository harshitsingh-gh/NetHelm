"""Family-1 generator — INTER-AREA SUMMARY-COST DISPLACEMENT (the `igp-summary-
default-nexthop` mechanism): an OSPF INTER-AREA Type-3 SUMMARY metric change, set
DIRECTLY via `area N range A.B.C.D/M cost C`, re-resolves an UNCHANGED BGP next-hop
across a DIFFERENT ABR, with ZERO BGP surface in the diff.

This is the third mechanism in the frozen quiet-half catalog (Family 1, BUILD_V1). It
is structurally DISTINCT from `igp-nh-metric-reroute` (the `generator_igp_metric`
sibling): that mechanism edits `ip ospf cost` on a TRANSIT LINK inside src's OWN area
(intra-area metric, src reads the egress /32 directly); THIS mechanism edits the metric
of an INTER-AREA Type-3 SUMMARY injected by an Area-Border-Router, and the egress
loopback /32 is GENUINELY SUPPRESSED behind the summary — so the SUMMARY, not the /32,
is the longest-prefix-match that recursively resolves the BGP NEXT_HOP. That is the
linchpin: a model under test must read the OSPF inter-area SUMMARY, not the /32. The
decisive change lives at an ABR under `router ospf` (`area 0 range ... cost C`) and acts
THROUGH the recursive next-hop resolution of a BGP route whose every attribute AND
best-path identity is byte-stable across the diff.

LIVE-VERIFIED on the pinned digest (batfish/allinone:nethelm @ sha256:09817554db90,
2026-06-15) — the BARE `area 0 range A.B.C.D/M cost C` form:
  (a) PARSES as CUMULUS_CONCATENATED with ZERO init issues (NOT unrecognized — the
      earlier "PARTIALLY_UNRECOGNIZED" docstring claim was FALSE; only the FRR-current
      `advertise cost C` variant is unrecognized on this digest);
  (b) SUPPRESSES the egress /32 at src — `routes(src, eg-lo/32)` returns 0 rows; only
      the ospfIA summary supernet is present, and it is the LPM that resolves the
      unchanged iBGP next-hop;
  (c) the `range cost C` value FLIPS which ABR src resolves eg-lo through (and thus the
      forward trace / waypoint): raising wabr's range cost (or lowering babr's) moves
      the supernet next-hop from wabr to babr, both ACCEPTED, nh-count = 1.
See knowledge/corpus/batfish/batfish_verified_facts.md ("FRR OSPF inter-area summary
(`area range`)") and knowledge/corpus/noc/ospf_summary_cost_nexthop_reroute.md.

Mechanism (RFC 4271 §9.1.2.2 (Breaking Ties, Phase 2) item (e) — "prefer the path
whose BGP NEXT_HOP is reachable at lower IGP metric"; resolved here via an OSPF
inter-area / Type-3 summary route): the customer /24 is learned by `src` over iBGP from
the egress `eg` with `eg`'s loopback as the BGP NEXT_HOP (the Batfish-honored outbound
route-map `set ip next-hop <eg-lo>` form — NOT bare `next-hop-self`, a documented no-op
on the pinned digest). `eg`'s loopback is NOT re-injected into BGP; it reaches `src`
ONLY through OSPF, and its /32 is suppressed behind a Type-3 summary injected by TWO
Area-Border-Routers:

  * `wabr` — the ABR whose path transits the inspection WAYPOINT (`wabr` itself).
  * `babr` — the BYPASS ABR.

Each ABR injects a Type-3 summary of `eg`'s loopback supernet into src's area via
`area 0 range <eg-lo-supernet>/M cost C` — and the `cost C` SETS the Type-3 metric
DIRECTLY (verified: it OVERRIDES the computed cost; the ABR's backbone interface cost
is irrelevant). `src`'s inter-area metric to the summary is therefore
(src->ABR area-1 link cost, equal+default on both legs) + (that ABR's configured
summary `cost C`), and the cheaper ABR wins.

  * PRE: the summary via `wabr` has STRICTLY lower cost, so `src` resolves eg-lo
    through `wabr` and src->customer transits the inspection node `wabr`.
  * DIFF: a single `area 0 range <supernet> cost <C>` line under one ABR's `router
    ospf` — RAISE `wabr`'s summary cost, or LOWER `babr`'s summary cost — framed as a
    routine capacity/latency retune of the inter-area summary metric. This is the
    documented operator knob for ABR preference steering (Cisco "OSPF inter-area route
    summarization"; FRR ospfd `area ... range ... cost`).
  * POST: the inter-area summary metric to eg-lo is strictly lower via `babr`,
    best-path re-resolves through `babr`, and src->customer silently bypasses `wabr`.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): an `area range cost` edit never
resets the BGP FSM (RFC 4271 §8: Established exits only on NOTIFICATION/hold-timer/TCP
teardown) and is not an OSPF adjacency parameter, so D1=∅. The /24 stays BEST and
installed in every RIB (only the recursive resolution of its UNCHANGED next-hop moves —
the eg-lo /32 is suppressed in BOTH snapshots, so its absence is not a D2 event in the
watch set; the SUMMARY moves cost/exit-ABR but stays present), so D2=∅; `babr`'s path
delivers exactly as `wabr`'s did (src->ABR->eg->dst, ACCEPTED in both snapshots), so
D3=∅, D7=∅. A STRICT (non-equal) inter-area summary-metric gap in BOTH snapshots means
exactly one best path each time (maximum-paths default 1, no equal-cost ECMP tie), so
D5=∅ and the oracle is byte-identical. The strict gap also means the decision is made
at the IGP-metric step BEFORE the nondeterministic router-id/age steps are reached (the
documented Batfish ECMP-multipath trap), which is what makes it deterministic AND keeps
D5 empty. (HAZARD, live-confirmed: EQUAL summary costs → OSPF installs BOTH next-hops
ECMP-width-2 → D5 FIRES and D4 degrades. The generator MUST hold a strict gap.)

PURITY GOTCHA (verified): the eg-lo /32 is GENUINELY ABSENT at src in both snapshots
(suppressed behind the range), so it must NOT be in the D2 watch set as a "must-stay-
present" /32 — the SUMMARY supernet is the resolver and IT stays present (only its
cost / exit-ABR moves). The final discriminator is the OSPF inter-area summary COST (a
strict metric) — so it dodges the router-id trap.

Topology (5 nodes; multi-area OSPF underlay, iBGP overlay in one AS reflected by `eg`,
eBGP to the customer AS)::

        area 1 (non-backbone)            area 0 (backbone)
        +-- wabr (ABR, WAYPOINT) --+
        |                          |
      src                          eg --(eBGP /30)-- dst   customer /24
        |                          |                       (dual-attached host on dst)
        +-- babr (ABR, BYPASS) ----+
              ^ KNOB: `area 0 range <eg-lo-supernet> cost C` under the ABR's router ospf

  * src, wabr, babr, eg are ONE AS (iBGP; `eg` is the route-reflector, reflecting the
    customer /24 to src + both ABRs with the outbound `set ip next-hop <eg-lo>`). dst
    is a separate AS (eBGP), originating the customer /24 on a connected dummy host.
  * src<->wabr and src<->babr are OSPF point-to-point /30 links in AREA 1 (non-
    backbone). wabr<->eg and babr<->eg are OSPF /30 links in AREA 0 (backbone). Each
    ABR is therefore area-1 on its src side and area-0 on its eg side (true ABR).
  * eg<->dst is the eBGP /30 link and is NOT in OSPF.
  * eg's loopback is in OSPF area 0 and is NOT advertised into BGP, so it reaches the
    core ONLY via OSPF — and each ABR summarizes it behind `area 0 range`, suppressing
    the /32 so the summary (not the /32) resolves the BGP next-hop at src.
  * src applies NO BGP policy; it has exactly one received path to the customer (from
    eg). The change edits ONE `area 0 range ... cost C` value on an ABR — zero BGP-
    namespace surface.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {raise_wabr, lower_babr} — two DIFFERENT inter-area summary-cost edits that
    both flip the egress off the waypoint, each on a DIFFERENT ABR / opposite
    direction:
      - raise_wabr : baseline summary cost(wabr) < cost(babr) (wabr summary wins). The
        change RAISES `wabr`'s summary cost above babr's, so babr's summary now wins.
        change_target = wabr.
      - lower_babr : same baseline. The change LOWERS `babr`'s summary cost below
        wabr's, so babr's summary now wins. Same outcome, opposite edit, a different
        ABR to read. change_target = babr.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually flips the recursive resolution. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of `area range cost` edit applied where it does NOT
        change the winner (raise the already-LOSING babr summary higher; lower the
        already-WINNING wabr summary lower). Ground truth is COMPLETELY EMPTY across
        ALL dimensions — the calibration trap (the model must predict an empty blast
        radius). The prose is indistinguishable in style from a bypass edit, AND the
        PRE snapshot is byte-identical across all four combos (same baseline summary
        costs) so the pre-state alone cannot classify bypass vs no_op.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_igp_metric): the
core ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer
/24, the non-backbone area id, the node base name, AND the OSPF summary-cost constants
are all drawn deterministically from the seed (random.Random(seed)). The summary-cost
draw PRESERVES the strict-gap invariant in BOTH snapshots (so D5 stays empty and the
decision is strict at the inter-area-metric step) while removing the fixed
{10,100,200,5,300} block that the audit flagged as a contamination fingerprint + a
no_op-calibration tell.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path
decision is STRICT at the inter-area-metric step in both snapshots (a real, non-equal
OSPF summary cost gap) — exactly one best path at src in each snapshot, no equal-cost
ECMP tie, maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

Live-verified (2026-06-15, pinned batfish/allinone:nethelm, real `area range cost`
knob): all 4 combos parse with zero init issues, 8/8 BGP sessions ESTABLISHED in both
snapshots; raise_wabr/bypass + lower_babr/bypass flip src->customer off wabr onto babr
(both ACCEPTED, nh-count 1 → D4 waypoint + D10 intent ONLY, D1/D2/D3/D5/D7=∅); both
*_no_op keep wabr on-path (COMPLETELY EMPTY); both bypass combos 10x byte-identical.

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

# Fixed area-1-side interface cost on each ABR (kept equal + cheap; the src->ABR legs
# are equal-cost so the ENTIRE discriminator lives in the `area range cost` summary
# metric, never in the src-side link). The summary metric at src =
# (src interface cost toward ABR, default) + (the ABR's configured `area range cost C`).
_AREA1_LINK_COST = 1
# Fixed backbone (eg-facing) interface cost on each ABR. IRRELEVANT to the summary
# metric (verified: `area range cost C` OVERRIDES the computed Type-3 metric) — kept
# fixed + equal so it is provably NOT the discriminator.
_BACKBONE_LINK_COST = 10


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
class _SummaryCosts:
    """The randomized-but-fixed-per-seed OSPF `area range cost` values, with the
    strict-gap invariant PRESERVED in both snapshots.

    Baseline (both snapshots' PRE): wabr_pre < babr_pre (strict) so wabr summary wins.
    bypass edits cross the gap; no_op edits widen the existing margin (winner unchanged).
    """

    wabr_pre: int          # baseline summary cost on wabr (the winner PRE)
    babr_pre: int          # baseline summary cost on babr (the loser PRE)
    wabr_raised: int       # raise_wabr/bypass: wabr -> this (> babr_pre) -> babr wins
    babr_lowered: int      # lower_babr/bypass: babr -> this (< wabr_pre) -> babr wins
    babr_raised: int       # raise_wabr/no_op: babr -> this (> babr_pre) -> wabr still wins
    wabr_lowered: int      # lower_babr/no_op: wabr -> this (< wabr_pre) -> wabr still wins


def _draw_summary_costs(rng: random.Random) -> _SummaryCosts:
    """Draw a strict-gap-preserving set of `area range cost` constants from ``rng``.

    OSPF cost is 0..16777215; we keep values comfortably inside [2, ~9000] with strict
    margins so every snapshot has a non-equal inter-area metric gap (no ECMP/D5) and
    the four edits land where the docstring claims:

        wabr_pre  <  babr_pre                          (PRE: wabr wins, strict)
        wabr_raised  >  babr_pre   (+ strict margin)   (bypass: babr wins)
        babr_lowered <  wabr_pre   (- strict margin)   (bypass: babr wins)
        babr_raised  >  babr_pre   (+ strict margin)   (no_op: wabr still wins, strict)
        wabr_lowered <  wabr_pre   (- strict margin)   (no_op: wabr still wins, strict)
        babr_lowered != wabr_lowered (the two "low" values are distinct from each other)

    The two "low" (below-wabr_pre) values need 2 distinct slots in [2, wabr_pre-1], so
    wabr_pre is drawn high enough (>= ~30) to guarantee that headroom; OSPF cost floor
    is 1, we keep >= 2.
    """
    margin = rng.randint(5, 40)            # strict separation unit
    # winner PRE: high enough that there are >=2 distinct slots strictly below it.
    wabr_pre = rng.randint(30, 120)
    babr_pre = wabr_pre + margin + rng.randint(5, 80)        # strictly > wabr_pre
    wabr_raised = babr_pre + margin + rng.randint(5, 80)     # strictly > babr_pre
    babr_raised = wabr_raised + margin + rng.randint(5, 80)  # higher still (inert)
    # Two DISTINCT values strictly below wabr_pre (both >= 2). babr_lowered is the
    # higher of the two; wabr_lowered is strictly below it.
    babr_lowered = rng.randint(4, wabr_pre - 2)             # in [4, wabr_pre-2]
    wabr_lowered = rng.randint(2, babr_lowered - 1)         # in [2, babr_lowered-1]
    # Final guards (the draws above satisfy these by construction; assert to be safe).
    assert 2 <= wabr_lowered < babr_lowered < wabr_pre < babr_pre < wabr_raised < babr_raised
    assert wabr_lowered != babr_lowered
    return _SummaryCosts(
        wabr_pre=wabr_pre, babr_pre=babr_pre, wabr_raised=wabr_raised,
        babr_lowered=babr_lowered, babr_raised=babr_raised, wabr_lowered=wabr_lowered,
    )


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
    costs: _SummaryCosts     # randomized strict-gap OSPF summary-cost constants


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

    costs = _draw_summary_costs(rng)

    return _Params(core_asn=core_asn, dst_asn=dst_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, area1=area1,
                   name=name, costs=costs)


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
    eg_lo_supernet: str       # the /30 that summarizes eg's loopback (suppresses the /32)


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

    # eg's loopback is at index .4 (rid_index["eg"]). The summary /30 covers .4..7
    # (eg=.4, dst=.5) — it covers eg-lo (the BGP next-hop to suppress) WITHOUT covering
    # src/wabr/babr loopbacks (.1/.2/.3), which must stay /32 for the iBGP mesh.
    eg_lo_supernet = f"{params.loop_block}.4/30"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip,
                 area1=params.area1, eg_lo_supernet=eg_lo_supernet)


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
    whichever ABR's inter-area summary to eg-lo is cheaper. The two src->ABR legs use
    the default OSPF cost (equal), so the discriminator is entirely the ABRs' summary
    `cost C`."""
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


def _abr_config(topo: _Topo, role: str, summary_cost: int) -> str:
    """wabr or babr: an ABR. eth1 (area1) toward src, eth2 (area0) toward eg. iBGP
    client of the reflector eg (so it learns + forwards the customer /24 with eg-lo as
    next-hop, resolved via its own area-0 route to eg-lo). The
    `area 0 range <eg-lo-supernet> cost C` under `router ospf` SUPPRESSES eg's /32 and
    SETS the Type-3 summary metric eg-lo gets into src's area DIRECTLY (verified: the
    `cost C` overrides the computed metric; the backbone interface cost is irrelevant) —
    this is the metric-bearing line this mechanism edits."""
    p = topo.params
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'src')]}/30"),
           ("eth2", f"{topo.ip[(role, 'eg')]}/30")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    # area1 toward src (cheap, fixed); area0 toward eg (fixed, NOT the discriminator).
    body.append(_ospf_iface("eth1", f"{topo.ip[(role, 'src')]}/30", topo.area1,
                            cost=_AREA1_LINK_COST))
    body.append(_ospf_iface("eth2", f"{topo.ip[(role, 'eg')]}/30", 0,
                            cost=_BACKBONE_LINK_COST))
    # The KNOB: the Type-3 summary of eg-lo's supernet, with its metric set DIRECTLY.
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n"
                f" area 0 range {topo.eg_lo_supernet} cost {summary_cost}\n!\n")
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
    customer /24 to the core with eg-lo as the recursive next-hop. CRUCIALLY eg does
    NOT advertise its OWN loopback into BGP — eg-lo reaches the core ONLY via OSPF
    (it is in area 0), so the ABRs' `area range` summary genuinely SUPPRESSES the /32
    and the summary becomes the LPM that resolves the BGP next-hop at src."""
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
    # NOTE: eg-lo is deliberately NOT advertised into BGP (it must reach the core via
    # OSPF only so the `area range` summary suppresses the /32 — the linchpin).
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
    c = topo.params.costs
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["wabr"]: _abr_config(topo, "wabr", c.wabr_pre),
        topo.name["babr"]: _abr_config(topo, "babr", c.babr_pre),
        topo.name["eg"]: _eg_config(topo),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# Which ABR each combo edits, and the before/after summary cost on it. Zero
# BGP-namespace surface (a single `area 0 range ... cost C` line under router ospf).
# --------------------------------------------------------------------------- #
def _change_plan(spec: IgpSummarySpec, costs: _SummaryCosts) -> tuple[str, int, int]:
    """Return (abr_role_to_edit, before_cost, after_cost) for the spec.

    raise_wabr/bypass : edit wabr  wabr_pre -> wabr_raised  (babr summary now wins)
    raise_wabr/no_op  : edit babr (already losing) babr_pre -> babr_raised (wabr wins, inert)
    lower_babr/bypass : edit babr  babr_pre -> babr_lowered (babr summary now wins)
    lower_babr/no_op  : edit wabr (already winning) wabr_pre -> wabr_lowered (wabr wins, inert)
    """
    knob, effect = spec.knob, spec.effect
    if knob == "raise_wabr":
        if effect == "bypass":
            return "wabr", costs.wabr_pre, costs.wabr_raised
        return "babr", costs.babr_pre, costs.babr_raised
    else:  # lower_babr
        if effect == "bypass":
            return "babr", costs.babr_pre, costs.babr_lowered
        return "wabr", costs.wabr_pre, costs.wabr_lowered


def _apply_change(topo: _Topo) -> tuple[str, str]:
    """Build the unified diff for the one `area range cost` edit. Returns
    (changed_node_name, patch)."""
    abr_role, before_cost, after_cost = _change_plan(topo.spec, topo.params.costs)
    node_name = topo.name[abr_role]
    before = _abr_config(topo, abr_role, before_cost)
    after = _abr_config(topo, abr_role, after_cost)

    old = f" area 0 range {topo.eg_lo_supernet} cost {before_cost}\n"
    new = f" area 0 range {topo.eg_lo_supernet} cost {after_cost}\n"
    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {topo.spec.dims_label()} on "
            f"{abr_role} (seed render drift)"
        )
    if before.replace(old, new, 1) != after:
        raise RuntimeError(
            f"change for {topo.spec.dims_label()} is not a single-line summary-cost swap"
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
# phrased the SAME way: the prose names only WHICH ABR's inter-area summary cost is
# edited and the value, never whether the recursive resolution / best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    abr_role, before_cost, after_cost = _change_plan(topo.spec, topo.params.costs)
    node = topo.name[abr_role]
    return (
        f"On `{node}` (AS{topo.params.core_asn}), change the OSPF inter-area summary "
        f"cost for the backbone aggregate `{topo.eg_lo_supernet}` from {before_cost} to "
        f"{after_cost} (a one-line `area 0 range {topo.eg_lo_supernet} cost <C>` edit "
        f"under `router ospf` — the Type-3 summary's metric input). See the diff."
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

    # D2 watch set: customer /24 + the three CORE loopbacks that MUST stay present
    # (src/wabr/babr — negative controls). eg-lo is DELIBERATELY EXCLUDED: it is
    # suppressed behind the `area range` in BOTH snapshots, so its /32 is genuinely
    # absent (the summary supernet resolves it). Including it would be a false D2.
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "wabr", "babr")] + [cust]

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
