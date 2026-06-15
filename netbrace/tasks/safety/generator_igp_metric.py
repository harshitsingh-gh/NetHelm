"""Family-1 generator — RECURSIVE UNDERLAY DISPLACEMENT (the `igp-nh-metric-reroute`
mechanism): an IGP-only OSPF cost edit re-resolves an UNCHANGED BGP next-hop off the
inspection waypoint, with ZERO BGP surface in the diff.

This is the flagship of the frozen quiet-half catalog (temporary/
frozen_quiet_half_scenario_set.md, Family 1). It is structurally distinct from the
`leak_ms_reroute` mechanism (which operates on PREFIX SPECIFICITY / longest-prefix
match) and from `lp_waypoint` (an explicit first-order BGP LOCAL_PREF edit all models
catch). Here the decisive change lives entirely in the IGP (OSPF), and acts THROUGH
the recursive next-hop resolution of a BGP route whose every attribute AND best-path
identity is byte-stable across the diff.

Mechanism (RFC 4271 §9.1.2.2 (Breaking Ties, Phase 2) item (e) — "prefer the path whose
BGP NEXT_HOP is reachable at lower IGP metric"; §9.1.2.2 uses lettered items, not
numbered steps; FRR bgp_path_info_cmp igp-metric step): `src` learns the
customer /24 over iBGP from BOTH `way` and `alt` with BYTE-IDENTICAL BGP attributes
(same LOCAL_PREF, same AS_PATH = [AS_dst], same ORIGIN, same MED, both iBGP). No BGP
attribute can decide, so best-path falls through to the IGP-metric tiebreak, resolving
each path's NEXT_HOP (the advertising egress's loopback, set via the Batfish-honored
outbound route-map `set ip next-hop <lo>` — NOT bare `next-hop-self`, which the pinned
digest treats as a no-op for eBGP-learned routes) recursively through the OSPF RIB.

  * PRE: OSPF cost src->way-lo is STRICTLY lower than src->alt-lo, so `way` wins and
    src->customer transits the inspection node `way`.
  * DIFF: a single `ip ospf cost` line on one of src's OSPF interfaces (raise the cost
    toward way, or lower it toward alt) — framed as a routine capacity/latency retune.
  * POST: the IGP metric to alt-lo is strictly lower, best-path re-resolves to `alt`,
    and src->customer silently bypasses `way`.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): an OSPF cost change never resets
the BGP FSM (RFC 4271 §8: Established exits only on NOTIFICATION/hold-timer/TCP
teardown) and is not an OSPF adjacency parameter, so D1=∅. The /24 stays BEST and
installed in every RIB (only its resolved next-hop moves), so D2=∅; `alt` delivers
exactly as `way` did, so D3=∅, D7=∅. A STRICT (non-equal) IGP cost gap in BOTH
snapshots means exactly one best path each time (maximum-paths default 1, no equal-cost
ECMP tie), so D5=∅ and the oracle is byte-identical. The strict gap also means the
decision is made at the IGP step BEFORE the nondeterministic router-id/age steps are
reached (the documented Batfish ECMP-multipath trap), which is what makes it
deterministic AND keeps D5 empty.

Topology (4 nodes; OSPF underlay between src and the two egresses, iBGP overlay in one
AS, eBGP to the customer AS)::

           OSPF cost (the KNOB) on src's interface toward each egress
        +----------------------------------------------------+
        |                                                    |
      src --(OSPF /30)-- way --(eBGP /30)-- dst   (the WAY / inspection path)
   (AS_core) |                               |
             |                               |   customer /24
             +-(OSPF /30)-- alt --(eBGP /30)-+   (originated by dst AS_dst,
                                                  dual-homed eBGP to way & alt)

  * src, way, alt are ONE AS (iBGP, OSPF speakers). dst is a separate AS (eBGP),
    originating the customer /24 on a connected dummy host.
  * src<->way and src<->alt are OSPF point-to-point /30 links (the only metric-bearing
    links; their cost is the tiebreak input). way<->dst and alt<->dst are eBGP /30
    links and are NOT in OSPF.
  * way and alt each eBGP-learn the customer /24 from dst and re-advertise it to src
    over iBGP, rewriting the NEXT_HOP to their OWN loopback via an outbound route-map
    `set ip next-hop <lo>`. src resolves that loopback recursively through OSPF, so the
    chosen egress is decided by the OSPF cost to the loopback (RFC 4271 §9.1.2.2 item (e)).
  * src applies NO BGP policy; the two received paths are attribute-tied. The change
    edits ONE `ip ospf cost` value on src — zero BGP-namespace surface.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone). The cost values below (10/100/200/5) are ILLUSTRATIVE only;
the actual OSPF costs are drawn per-seed (see _draw_link_costs) preserving the strict
gap `way_lowered < alt_lowered < way_pre < alt_pre < way_raised < alt_raised`, so the
edited interface's pre-cost alone CANNOT classify bypass vs no_op:

  * knob ∈ {raise_way, lower_alt} — two DIFFERENT OSPF cost edits that both flip the
    egress off the waypoint, each on a different src interface / opposite direction:
      - raise_way : baseline cost(src->way)=way_pre < cost(src->alt)=alt_pre (way wins);
        the change RAISES src's cost toward way to way_raised (> alt_pre), so alt now
        wins (illustratively 10 < 100, raised to 200 > 100).
      - lower_alt : same baseline; the change LOWERS src's cost toward alt to alt_lowered
        (< way_pre), so alt now wins (illustratively raised-side 5 < 10). Same outcome,
        opposite edit, different interface to read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually flips the recursive resolution. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of `ip ospf cost` edit applied where it does NOT change
        the winner (raise the already-losing alt-side cost higher; lower the
        already-winning way-side cost lower). Ground truth is COMPLETELY EMPTY across
        ALL dimensions — the calibration trap (the model must predict an empty blast
        radius). The prose is indistinguishable in style from a bypass edit.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): the core
ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer /24,
the node base name, AND the six OSPF cost values (_draw_link_costs, a strict-gap-
preserving 6-strictly-increasing-value draw) are all drawn deterministically from the
seed. Randomizing the costs per-seed removes the hardcoded {10,100,200,5,300}
contamination/memorization fingerprint and ensures the edited interface's pre-cost
alone does not classify bypass vs no_op.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path
decision is STRICT at the IGP-metric step in both snapshots (a real, non-equal OSPF
cost gap) — exactly one best path at src in each snapshot, no equal-cost ECMP tie,
maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

Public API mirrors generator_lp:
    generate_igp_metric_suite(n, base_seed=...)        -> list[Scenario]
    generate_igp_metric_all_combos(seed=...)           -> list[Scenario]
    generate_igp_metric_instance(seed, spec=None)      -> Scenario
    enumerate_specs() / enumerable_count()
"""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass
from typing import Optional

from netbrace.tasks.safety.scenarios import IntentInvariant, Scenario
from netbrace.tasks.safety import _role_position as _rp
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

@dataclass(frozen=True)
class IgpMetricSpec:
    """A point in the Family-1 igp-metric generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[IgpMetricSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[IgpMetricSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(IgpMetricSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the core (src/way/alt share
# one AS -> iBGP) and the customer AS (dst). Clear of the hand-authored 65000 family.
_ASN_LO, _ASN_HI = 4_200_200_000, 4_200_299_999

_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]

_ROLES = ("src", "way", "alt", "dst")


@dataclass(frozen=True)
class _LinkCosts:
    """The randomized-but-fixed-per-seed `ip ospf cost` values on src's two underlay
    interfaces, with the strict-gap invariant PRESERVED in both snapshots.

    Baseline (both snapshots' PRE): way_pre < alt_pre (strict) so the way side wins.
    bypass edits cross the gap (flip the winner); no_op edits widen the existing margin
    in the inert direction (winner unchanged). The six values are STRICTLY increasing:

        way_lowered < alt_lowered < way_pre < alt_pre < way_raised < alt_raised

    so the edited interface's pre-cost (way_pre or alt_pre) ALONE cannot classify bypass
    vs no_op — exactly the memorization fingerprint the per-seed draw removes.
    """

    way_pre: int        # baseline cost on src->way (the winner PRE)
    alt_pre: int        # baseline cost on src->alt (the loser PRE)
    way_raised: int     # raise_way/bypass: way -> this (> alt_pre) -> alt wins (flip)
    alt_lowered: int    # lower_alt/bypass: alt -> this (< way_pre) -> alt wins (flip)
    alt_raised: int     # raise_way/no_op:  alt -> this (> alt_pre) -> way still wins (inert)
    way_lowered: int    # lower_alt/no_op:  way -> this (< way_pre) -> way still wins (inert)


def _draw_link_costs(rng: random.Random) -> _LinkCosts:
    """Draw a strict-gap-preserving set of `ip ospf cost` constants from ``rng``.

    OSPF cost is 1..65535 on FRR; we keep values comfortably inside [2, ~9000] with
    strict margins so every snapshot has a non-equal underlay metric gap (no ECMP/D5)
    and the four edits land where the docstring claims:

        way_pre  <  alt_pre                          (PRE: way wins, strict)
        way_raised  >  alt_pre   (+ strict margin)   (bypass: alt wins)
        alt_lowered <  way_pre   (- strict margin)   (bypass: alt wins)
        alt_raised  >  alt_pre   (+ strict margin)   (no_op: way still wins, strict)
        way_lowered <  way_pre   (- strict margin)   (no_op: way still wins, strict)
        alt_lowered != way_lowered (the two "low" values are distinct from each other)

    The two "low" (below-way_pre) values need 2 distinct slots in [2, way_pre-1], so
    way_pre is drawn high enough (>= ~30) to guarantee that headroom; the OSPF cost
    floor is 1, we keep >= 2.
    """
    margin = rng.randint(5, 40)            # strict separation unit
    # winner PRE: high enough that there are >=2 distinct slots strictly below it.
    way_pre = rng.randint(30, 120)
    alt_pre = way_pre + margin + rng.randint(5, 80)        # strictly > way_pre
    way_raised = alt_pre + margin + rng.randint(5, 80)     # strictly > alt_pre
    alt_raised = way_raised + margin + rng.randint(5, 80)  # higher still (inert)
    # Two DISTINCT values strictly below way_pre (both >= 2). alt_lowered is the
    # higher of the two; way_lowered is strictly below it.
    alt_lowered = rng.randint(4, way_pre - 2)             # in [4, way_pre-2]
    way_lowered = rng.randint(2, alt_lowered - 1)         # in [2, alt_lowered-1]
    # Final guards (the draws above satisfy these by construction; assert to be safe).
    assert 2 <= way_lowered < alt_lowered < way_pre < alt_pre < way_raised < alt_raised
    assert way_lowered != alt_lowered
    return _LinkCosts(
        way_pre=way_pre, alt_pre=alt_pre, way_raised=way_raised,
        alt_lowered=alt_lowered, alt_raised=alt_raised, way_lowered=way_lowered,
    )


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    core_asn: int            # src/way/alt share this (iBGP)
    dst_asn: int             # the customer AS (eBGP)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string
    costs: _LinkCosts        # randomized strict-gap OSPF underlay-cost constants
    swap: bool               # per-seed: exchange the way<->alt PHYSICAL slot (leak fix)


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

    # Drawn LAST so the ASN/IP/name addressing above stays byte-identical to before.
    costs = _draw_link_costs(rng)

    # Per-seed ROLE->POSITION swap (positional-leak fix): decides which PHYSICAL slot
    # (src interface index eth1/eth2, loopback octet, name suffix, node order) the
    # waypoint role `way` vs the bypass role `alt` occupies.
    swap = _rp.draw_swap(rng)

    return _Params(core_asn=core_asn, dst_asn=dst_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, name=name,
                   costs=costs, swap=swap)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: IgpMetricSpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str
    src_iface: dict[str, str]   # role -> the eth on SRC toward that egress (swap-driven)


def _build_topo(spec: IgpMetricSpec, params: _Params) -> _Topo:
    rid_index = _rp.swapped_rid_index(
        {"src": 1, "way": 2, "alt": 3, "dst": 4}, params.swap, ("way", "alt"))
    name = _rp.swapped_names(dict(params.name), params.swap, ("way", "alt"))
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved by the (swapped) physical slot: the role on physical
    # slot 2 takes src-iface eth1 (base .0) and dst-link base .8; the slot-3 role takes
    # eth2 (base .4) and base .12. So the eth index / link IPs of the WAYPOINT side move
    # per seed -- the edited-interface identity carries no trap/no_op label info.
    lo_role = "way" if rid_index["way"] == 2 else "alt"   # role on physical slot 2 -> eth1
    hi_role = "alt" if lo_role == "way" else "way"        # role on physical slot 3 -> eth2
    src_iface = {lo_role: "eth1", hi_role: "eth2"}
    ip: dict[tuple[str, str], str] = {
        ("src", lo_role): addr(1), (lo_role, "src"): addr(2),
        ("src", hi_role): addr(5), (hi_role, "src"): addr(6),
        (lo_role, "dst"): addr(9), ("dst", lo_role): addr(10),
        (hi_role, "dst"): addr(13), ("dst", hi_role): addr(14),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip,
                 src_iface=src_iface)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 format). OSPF on the src<->egress links + loopbacks; eBGP /30s
# are NOT in OSPF; iBGP over loopbacks; egress next-hop rewrite via outbound route-map.
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


def _src_config(topo: _Topo, *, cost_way: int, cost_alt: int) -> str:
    """src: OSPF to way+alt (the metric-bearing links carry the KNOB), iBGP to both,
    no BGP policy. The two received customer paths are attribute-tied.

    Interfaces are rendered by PHYSICAL eth order (eth1 = the role on physical slot 2,
    eth2 = the role on slot 3) -- which is swap-driven per seed -- while each interface
    carries its LOGICAL role's cost. So `eth1` is the waypoint-side link in ~half the
    seeds and the bypass-side link in the other half: the edited interface's identity
    no longer predicts the trap/no_op label."""
    p = topo.params
    lo = topo.loopback["src"]
    way_eth, alt_eth = topo.src_iface["way"], topo.src_iface["alt"]
    cost_of = {way_eth: cost_way, alt_eth: cost_alt}
    # eth1 then eth2 in fixed physical order; each maps to whichever role's link it carries.
    eth_phys = [("eth1", "eth1"), ("eth2", "eth2")]
    role_of_eth = {way_eth: "way", alt_eth: "alt"}
    eth = [(e, f"{topo.ip[('src', role_of_eth[e])]}/30") for e, _ in eth_phys]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    for e, _ in eth_phys:
        body.append(_ospf_iface(e, f"{topo.ip[('src', role_of_eth[e])]}/30", cost_of[e]))
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.loopback['way']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['way']} update-source lo\n")
    body.append(f" neighbor {topo.loopback['alt']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['alt']} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _egress_config(topo: _Topo, role: str) -> str:
    """way or alt: OSPF to src (metric link), eBGP to dst (no OSPF), iBGP to src + the
    other egress with an OUTBOUND `set ip next-hop <own-lo>` toward src (the
    Batfish-honored next-hop-self form). Re-advertises dst's customer /24 to src."""
    p = topo.params
    other = "alt" if role == "way" else "way"
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'src')]}/30"),
           ("eth2", f"{topo.ip[(role, 'dst')]}/30")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[(role, 'src')]}/30"))    # OSPF underlay
    body.append(_plain_iface("eth2", f"{topo.ip[(role, 'dst')]}/30"))  # eBGP link, no OSPF
    body.append(f"route-map NHS_OUT permit 10\n set ip next-hop {lo}\n!\n")
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    # iBGP to src (next-hop-self via route-map) and to the other egress.
    body.append(f" neighbor {topo.loopback['src']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['src']} update-source lo\n")
    body.append(f" neighbor {topo.loopback[other]} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback[other]} update-source lo\n")
    # eBGP to dst (directly-connected link IP).
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.dst_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  neighbor {topo.loopback['src']} route-map NHS_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo) -> str:
    """dst: the customer AS, eBGP to way + alt, originates the customer /24 + its lo."""
    p = topo.params
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}/30"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}/30")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["dst"], lo, eth, dummies), _frr_header(topo.name["dst"])]
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
    c = topo.params.costs
    return {
        topo.name["src"]: _src_config(topo, cost_way=c.way_pre, cost_alt=c.alt_pre),
        topo.name["way"]: _egress_config(topo, "way"),
        topo.name["alt"]: _egress_config(topo, "alt"),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change: a single `ip ospf cost` edit on src. Zero BGP-namespace surface.
# --------------------------------------------------------------------------- #
def _apply_change(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    c = topo.params.costs
    before = _src_config(topo, cost_way=c.way_pre, cost_alt=c.alt_pre)

    if knob == "raise_way":
        # bypass: raise src->way cost way_pre->way_raised (alt's alt_pre now wins).
        # no_op : raise src->alt cost alt_pre->alt_raised (alt was already losing; way wins).
        if effect == "bypass":
            old = f" ip ospf cost {c.way_pre}\n"
            new = f" ip ospf cost {c.way_raised}\n"
            after = _src_config(topo, cost_way=c.way_raised, cost_alt=c.alt_pre)
        else:
            old = f" ip ospf cost {c.alt_pre}\n"
            new = f" ip ospf cost {c.alt_raised}\n"
            after = _src_config(topo, cost_way=c.way_pre, cost_alt=c.alt_raised)
    else:  # lower_alt
        # bypass: lower src->alt cost alt_pre->alt_lowered (alt now beats way's way_pre).
        # no_op : lower src->way cost way_pre->way_lowered (way was already winning; still wins).
        if effect == "bypass":
            old = f" ip ospf cost {c.alt_pre}\n"
            new = f" ip ospf cost {c.alt_lowered}\n"
            after = _src_config(topo, cost_way=c.way_pre, cost_alt=c.alt_lowered)
        else:
            old = f" ip ospf cost {c.way_pre}\n"
            new = f" ip ospf cost {c.way_lowered}\n"
            after = _src_config(topo, cost_way=c.way_lowered, cost_alt=c.alt_pre)

    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {topo.spec.dims_label()} on src "
            f"(seed render drift)"
        )
    # Sanity: the rebuilt `after` config must equal a single in-place value swap.
    if before.replace(old, new, 1) != after:
        raise RuntimeError(
            f"change for {topo.spec.dims_label()} is not a single-line cost swap"
        )
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
# Prose (CONFIG EDIT + INTENT ONLY — never the routing OUTCOME). bypass and no_op are
# phrased the SAME way: the prose names only WHICH interface's OSPF cost is edited and
# the value, never whether the recursive resolution / best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    src = topo.name["src"]
    c = topo.params.costs
    # The edited LOGICAL role (way-side or alt-side cost) per (knob, effect); the actual
    # interface name is whichever eth that role's link occupies this seed (swap-driven),
    # so the named interface carries no trap/no_op tell.
    if knob == "raise_way":
        edited_role = "way" if effect == "bypass" else "alt"
        frm = c.way_pre if effect == "bypass" else c.alt_pre
        to = c.way_raised if effect == "bypass" else c.alt_raised
    else:  # lower_alt
        edited_role = "alt" if effect == "bypass" else "way"
        frm = c.alt_pre if effect == "bypass" else c.way_pre
        to = c.alt_lowered if effect == "bypass" else c.way_lowered
    iface = topo.src_iface[edited_role]
    return (
        f"On `{src}` (AS{topo.params.core_asn}), change the OSPF interface cost on "
        f"`{iface}` from {frm} to {to} (a one-line `ip ospf cost` edit). See the diff."
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
def _scenario_from_spec(spec: IgpMetricSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the three core loopbacks (negative controls).
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "way", "alt")] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host.
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint, restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"igp-metric quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_igp_metric_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    node_rng = random.Random(f"igp_metric_nodes_{seed}")
    nodes = [src, way, alt, dst]
    node_rng.shuffle(nodes)

    return Scenario(
        name=name,
        nodes=nodes,
        pre_configs=pre,
        change_target=src,
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
# Public API (mirrors generator_lp).
# --------------------------------------------------------------------------- #
def generate_igp_metric_instance(seed: int, spec: Optional[IgpMetricSpec] = None) -> Scenario:
    """Emit ONE Family-1 igp-metric instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[IgpMetricSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_igp_metric_all_combos(*, seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_igp_metric_suite(n: int, *, base_seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct
    seed per position; wrap with a fresh seed offset when ``n`` exceeds the combo
    count, giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
