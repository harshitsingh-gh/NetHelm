"""Family-1 generator — REDISTRIBUTE / ADMINISTRATIVE-DISTANCE SHADOW REROUTE (the
`redistribute-ad-shadow-reroute` mechanism): an OSPF-namespace redistribution edit
makes a redistributed OSPF copy of the customer prefix (administrative distance 110)
out-prefer the iBGP-learned copy (administrative distance 200) in `src`'s main RIB, so
the INSTALLED forwarding path moves off the inspection waypoint — with ZERO BGP-namespace
surface in the diff. The decisive change lives entirely in the OSPF `redistribute`
config; the BGP best-path / RIB at every node is byte-stable across the diff.

This is a sibling of the `igp-nh-metric-reroute` mechanism (generator_igp_metric) — both
keep the BGP layer untouched and flip the INSTALLED next-hop through the IGP — but the
decision is made at a DIFFERENT control-plane step. There, an OSPF *cost* re-resolves an
UNCHANGED iBGP best-path's recursive next-hop (RFC 4271 §9.1.2.2 step 6, IGP-metric
tiebreak). Here, an OSPF *redistribution* injects a SECOND, independent copy of the same
prefix into the main RIB at a LOWER administrative distance, and the RIB's
protocol-preference arbitration (FRR/zebra route-manager: lowest AD wins; OSPF intra/
external 110 < iBGP 200) EVICTS the iBGP copy outright. The iBGP route is still BEST in
the BGP RIB — it just loses the main-RIB install to the OSPF copy. That is a strictly
different reading task (administrative-distance arbitration between two protocols), not a
clone.

Mechanism (administrative distance / RIB protocol preference — IOS/FRR default AD: eBGP
20 < OSPF 110 < iBGP 200; FRR zebra installs the lowest-AD copy of a prefix into the
main RIB): `src` learns the customer /24 over iBGP ONLY from `way` (NEXT_HOP rewritten to
way's loopback via the Batfish-honored outbound route-map `set ip next-hop <lo>` — NOT
bare `next-hop-self`, a documented no-op on the pinned digest for eBGP-learned routes),
resolved recursively through OSPF — AD 200. `alt` eBGP-learns the SAME /24 from `dst`
(so it can deliver) and can REDISTRIBUTE that BGP route into OSPF, where it reaches `src`
as an OSPF external (E2) route at AD 110.

  * PRE: no redistributed OSPF copy of the customer /24 exists at `src`, so the only
    installed copy is the iBGP route (AD 200) via `way`; src->customer transits the
    inspection node `way`.
  * DIFF: a single OSPF-namespace edit on `alt` (add the `redistribute bgp route-map …`
    line, OR widen the redistribution route-map's prefix-list to cover the customer /24)
    — framed as a routine "advertise the customer block into the IGP" / scope retune.
  * POST: the OSPF copy (AD 110) is now present at `src` and EVICTS the iBGP copy
    (AD 200) from the main RIB, so the installed next-hop re-resolves to `alt` and
    src->customer silently bypasses `way`.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): a `redistribute` edit on `alt` is
not an iBGP/eBGP session parameter and never resets a BGP FSM (RFC 4271 §8: Established
exits only on NOTIFICATION/hold-timer/TCP teardown), so D1=∅. The /24 stays present-and-
installed in every RIB across the diff (only WHICH protocol's copy is installed at src
changes — and `dst`'s own origin + `way`'s/`alt`'s eBGP copies are untouched), so D2=∅;
`alt` delivers the /24 exactly as `way` did (a real, verified path), so D3=∅, D7=∅. The
iBGP copy is a SINGLE route via `way` PRE (only `way` re-advertises it over iBGP; `alt`'s
outbound to src DENIES the customer prefix so there is no second iBGP copy → no
equal-cost iBGP ECMP), and the OSPF copy is a single E2 route POST, so there is exactly
one installed best path in each snapshot — D5=∅ and the oracle is byte-identical. The AD
gap (110 vs 200) is STRICT and resolved at the administrative-distance step BEFORE any
router-id/age tiebreak is reached (the documented Batfish ECMP-multipath trap), which is
what makes it deterministic AND keeps D5 empty.

Topology (4 nodes; OSPF underlay between src and the two egresses, iBGP overlay in one
AS, eBGP to the customer AS — identical shape to generator_igp_metric)::

      src --(OSPF /30)-- way --(eBGP /30)-- dst   (the WAY / inspection path; iBGP /24)
   (AS_core) |                               |
             |                               |   customer /24
             +-(OSPF /30)-- alt --(eBGP /30)-+   (originated by dst AS_dst, dual-homed
                                                  eBGP to way & alt; the AD-shadow copy
                                                  is redistributed into OSPF by `alt`)

  * src, way, alt are ONE AS (iBGP, OSPF speakers). dst is a separate AS (eBGP),
    originating the customer /24 on a connected dummy host.
  * src<->way and src<->alt are OSPF point-to-point /30 links. way<->dst and alt<->dst
    are eBGP /30 links and are NOT in OSPF.
  * `way` eBGP-learns the /24 from dst and re-advertises it to src over iBGP, rewriting
    the NEXT_HOP to its OWN loopback via `set ip next-hop <lo>`. src resolves that
    loopback recursively through OSPF → AD 200, transit via way.
  * `alt` eBGP-learns the /24 from dst (AD 20, so it can deliver) but its outbound
    toward src DENIES the customer /24 (so it is NOT a second iBGP copy at src). `alt`
    can redistribute its BGP routes into OSPF; the redistribution is the KNOB.
  * src applies NO BGP policy and makes NO change. The change edits ONE OSPF-namespace
    construct on `alt` — zero BGP-namespace surface.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {enable_redist, scope_redist} — two DIFFERENT OSPF-namespace edits that both
    introduce the AD-110 OSPF copy of the customer /24 at src:
      - enable_redist : PRE has NO `redistribute bgp …` line under `router ospf` on
        `alt`. The change ADDS `redistribute bgp route-map REDIST_CUST` (the route-map's
        prefix-list already matches the customer /24). Reading task: "is there a
        redistribute statement, and what does its route-map permit?"
      - scope_redist  : PRE already HAS `redistribute bgp route-map REDIST_CUST`, but the
        route-map's prefix-list (REDIST_PL) matches a benign placeholder (alt's connected
        /30 supernet), so the customer /24 is NOT redistributed. The change EDITS that
        one prefix-list line to permit the customer /24. Reading task: "what network does
        the redistribution route-map's prefix-list actually match?"

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually introduces the AD-110 copy that evicts the iBGP route.
        D4+D10 fire; D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of edit applied so it does NOT introduce a customer-/24
        OSPF copy — enable_redist/no_op ADDS the redistribute line but scoped to a
        benign placeholder /30 (the customer /24 stays un-redistributed); scope_redist/
        no_op edits the prefix-list from one benign placeholder /30 to ANOTHER (still
        not the customer /24). iBGP (AD 200) keeps winning via way; ground truth is
        COMPLETELY EMPTY across ALL dimensions (the model must predict an empty blast
        radius). The prose is indistinguishable in style from a bypass edit.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_igp_metric): the
core ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer
/24, and the node base name are all drawn deterministically from the seed.

Determinism contract (oracle_determinism_spec class STATIC-DET): exactly one installed
best path at src in each snapshot (PRE: a single iBGP route via way; POST/bypass: a
single OSPF E2 route via alt), no equal-cost ECMP tie, decided at the
administrative-distance step before router-id/age. D4 is scored by
ExtendedOracle._waypoint_diff as the all-traces-transit invariant; D10 by the matching
kind="waypoint" IntentInvariant.

LIVE-VERIFIED (2026-06-14, pinned batfish/allinone:nethelm @ 09817554db90, network
"netbrace_build_redistribute_ad"): the OSPF E2 copy (AD 110) evicts the iBGP copy
(AD 200) in the FRR main RIB; bypass combos → {waypoint, intent} ONLY (D1/D2/D3/D5/D7
= ∅), reachability preserved via alt; no_op combos → COMPLETELY EMPTY; bypass combos
10x byte-identical.

Public API mirrors generator_igp_metric:
    generate_redistribute_ad_suite(n, base_seed=...)        -> list[Scenario]
    generate_redistribute_ad_all_combos(seed=...)           -> list[Scenario]
    generate_redistribute_ad_instance(seed, spec=None)      -> Scenario
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
KNOB_VALUES = ("enable_redist", "scope_redist")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}


@dataclass(frozen=True)
class RedistributeAdSpec:
    """A point in the Family-1 redistribute-ad generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[RedistributeAdSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[RedistributeAdSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(RedistributeAdSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the core (src/way/alt share
# one AS -> iBGP) and the customer AS (dst). Clear of the hand-authored 65000 family.
_ASN_LO, _ASN_HI = 4_200_300_000, 4_200_399_999

_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]

_ROLES = ("src", "way", "alt", "dst")


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    core_asn: int            # src/way/alt share this (iBGP)
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
    link_block = (172, rng.randint(16, 31), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    return _Params(core_asn=core_asn, dst_asn=dst_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, name=name)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: RedistributeAdSpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str
    # Two OFF-PATH /24 DECOYS the redistribution scope points at when it is NOT the
    # customer /24 (FB-4 mask-length leak fix). Each is a real /24 alt holds on its OWN
    # connected dummy interface, so the prefix-list match is non-vacuous (it matches alt's
    # connected route) yet is NOT the customer /24 -> redistributing it injects NO AD-shadow
    # copy of the customer prefix at src. Crucially each is a /24 (SAME mask as the customer
    # /24), so mask length carries zero bypass/no_op label info; the discriminator is WHICH
    # /24 (on-path customer vs off-path decoy), which needs routing reasoning.
    decoy_a_ip: str      # host IP of decoy /24 A (alt dummy dum1)
    decoy_b_ip: str      # host IP of decoy /24 B (alt dummy dum2)
    placeholder_a: str   # decoy /24 A "<net>.0/24"
    placeholder_b: str   # decoy /24 B "<net>.0/24"


def _supernet30(addr_off1: str) -> str:
    """The /30 supernet base from any of its host IPs (e.g. .13 -> .12/30)."""
    a, b, c, d = (int(x) for x in addr_off1.split("."))
    base = (d // 4) * 4
    return f"{a}.{b}.{c}.{base}/30"


def _build_topo(spec: RedistributeAdSpec, params: _Params) -> _Topo:
    name = dict(params.name)
    rid_index = {"src": 1, "way": 2, "alt": 3, "dst": 4}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved from the link block:
    #   src-way base .0  (src=.1, way=.2)   OSPF
    #   src-alt base .4  (src=.5, alt=.6)   OSPF
    #   way-dst base .8  (way=.9, dst=.10)  eBGP
    #   alt-dst base .12 (alt=.13, dst=.14) eBGP
    ip: dict[tuple[str, str], str] = {
        ("src", "way"): addr(1), ("way", "src"): addr(2),
        ("src", "alt"): addr(5), ("alt", "src"): addr(6),
        ("way", "dst"): addr(9), ("dst", "way"): addr(10),
        ("alt", "dst"): addr(13), ("dst", "alt"): addr(14),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    # Two OFF-PATH /24 decoys (FB-4 fix), drawn from the SAME customer-prefix pools (a
    # different third octet than the customer /24) so the decoy /24 and the customer /24
    # share ADDRESS FAMILY -> a "which /8 / which pool?" probe carries no label info. Only
    # WHICH /24 (the on-path customer vs an off-path decoy) separates bypass from no_op.
    a, b, c = params.customer_net.split(".")
    decoy_a_net = f"{a}.{b}.{(int(c) + 11) % 256}"
    decoy_b_net = f"{a}.{b}.{(int(c) + 23) % 256}"
    # guard: never alias the customer /24 (distinct third octet by construction above,
    # but assert in case of wrap collisions on the boundary).
    if decoy_a_net == params.customer_net:
        decoy_a_net = f"{a}.{b}.{(int(c) + 37) % 256}"
    if decoy_b_net in (params.customer_net, decoy_a_net):
        decoy_b_net = f"{a}.{b}.{(int(c) + 53) % 256}"
    decoy_a_ip = f"{decoy_a_net}.1"
    decoy_b_ip = f"{decoy_b_net}.1"
    placeholder_a = f"{decoy_a_net}.0/24"
    placeholder_b = f"{decoy_b_net}.0/24"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip,
                 decoy_a_ip=decoy_a_ip, decoy_b_ip=decoy_b_ip,
                 placeholder_a=placeholder_a, placeholder_b=placeholder_b)


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


def _ospf_iface(iface: str, ipm: str) -> str:
    lines = [f"interface {iface}", f" ip address {ipm}",
             " ip ospf area 0", " ip ospf network point-to-point", "!"]
    return "\n".join(lines) + "\n"


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


def _src_config(topo: _Topo) -> str:
    """src: OSPF to way+alt, iBGP to both, NO BGP policy, NO change. Learns the
    customer /24 over iBGP from `way` only (AD 200), resolved recursively via OSPF."""
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'way')]}/30"),
           ("eth2", f"{topo.ip[('src', 'alt')]}/30")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('src', 'way')]}/30"))
    body.append(_ospf_iface("eth2", f"{topo.ip[('src', 'alt')]}/30"))
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


def _way_config(topo: _Topo) -> str:
    """way: OSPF to src, eBGP to dst (no OSPF), iBGP to src + alt. Re-advertises dst's
    customer /24 to src over iBGP with the next-hop rewritten to its OWN loopback
    (the Batfish-honored `set ip next-hop <lo>` form). This is the AD-200 copy."""
    p = topo.params
    lo = topo.loopback["way"]
    eth = [("eth1", f"{topo.ip[('way', 'src')]}/30"),
           ("eth2", f"{topo.ip[('way', 'dst')]}/30")]
    body = [_iface_header(topo.name["way"], lo, eth, []), _frr_header(topo.name["way"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('way', 'src')]}/30"))   # OSPF underlay
    body.append(_plain_iface("eth2", f"{topo.ip[('way', 'dst')]}/30"))  # eBGP link, no OSPF
    body.append(f"route-map NHS_OUT permit 10\n set ip next-hop {lo}\n!\n")
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.loopback['src']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['src']} update-source lo\n")
    body.append(f" neighbor {topo.loopback['alt']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['alt']} update-source lo\n")
    body.append(f" neighbor {topo.ip[('dst', 'way')]} remote-as {p.dst_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  neighbor {topo.loopback['src']} route-map NHS_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _alt_config(topo: _Topo, *, redist_present: bool, redist_match: str) -> str:
    """alt: OSPF to src, eBGP to dst (no OSPF), iBGP to src + way. eBGP-learns the
    customer /24 from dst (AD 20 — so alt can DELIVER) but its outbound toward src
    DENIES the customer /24 (so it is NOT a second iBGP copy at src). The KNOB is the
    `redistribute bgp route-map REDIST_CUST` line and the REDIST_PL prefix-list it
    matches: when REDIST_PL permits the customer /24 AND the redistribute line is
    present, alt injects an OSPF external (E2) copy of the /24 at AD 110.

    ``redist_present`` -> whether the `redistribute bgp route-map REDIST_CUST` line is
    under `router ospf`. ``redist_match`` -> the single network REDIST_PL permits.
    """
    p = topo.params
    lo = topo.loopback["alt"]
    eth = [("eth1", f"{topo.ip[('alt', 'src')]}/30"),
           ("eth2", f"{topo.ip[('alt', 'dst')]}/30")]
    # Two OFF-PATH /24 decoys on connected dummies (FB-4 mask fix): real present
    # routes the redistribution prefix-list can point at, both /24 (same mask as the
    # customer /24) so mask length carries no label info; neither is the customer /24,
    # so a redistribute filtered to them injects no customer-prefix OSPF copy at src.
    decoys = [("dum1", f"{topo.decoy_a_ip}/24"), ("dum2", f"{topo.decoy_b_ip}/24")]
    body = [_iface_header(topo.name["alt"], lo, eth, decoys), _frr_header(topo.name["alt"])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[('alt', 'src')]}/30"))   # OSPF underlay
    body.append(_plain_iface("eth2", f"{topo.ip[('alt', 'dst')]}/30"))  # eBGP link, no OSPF
    body.append(_plain_iface("dum1", f"{topo.decoy_a_ip}/24"))          # off-path decoy /24 A
    body.append(_plain_iface("dum2", f"{topo.decoy_b_ip}/24"))          # off-path decoy /24 B
    # REDIST_PL: the (knob-controlled) network the redistribution route-map matches.
    body.append(f"ip prefix-list REDIST_PL seq 5 permit {redist_match}\n!\n")
    # CUST_DENY_PL: ALWAYS the customer /24 — the FIXED filter that stops alt from
    # iBGP-advertising the customer /24 to src (so PRE has a single iBGP copy via way).
    body.append(f"ip prefix-list CUST_DENY_PL seq 5 permit {topo.customer_prefix}\n!\n")
    body.append("route-map REDIST_CUST permit 10\n match ip address prefix-list REDIST_PL\n!\n")
    body.append("route-map NHS_OUT deny 10\n match ip address prefix-list CUST_DENY_PL\n!\n")
    body.append(f"route-map NHS_OUT permit 20\n set ip next-hop {lo}\n!\n")
    ospf = [f"router ospf", f" ospf router-id {lo}", " passive-interface lo"]
    if redist_present:
        ospf.append(" redistribute bgp route-map REDIST_CUST")
    ospf.append("!")
    body.append("\n".join(ospf) + "\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.loopback['src']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['src']} update-source lo\n")
    body.append(f" neighbor {topo.loopback['way']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['way']} update-source lo\n")
    body.append(f" neighbor {topo.ip[('dst', 'alt')]} remote-as {p.dst_asn}\n")
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


# --------------------------------------------------------------------------- #
# Per-(knob,effect) PRE redistribution state (the alt config is the only one that
# varies). The DIFF target is ALWAYS `alt`; every other node is byte-stable.
#
#   knob=enable_redist : PRE has NO redistribute line; the diff ADDS it.
#       bypass -> REDIST_PL permits the customer /24 (so the added redistribute injects
#                 the AD-110 copy -> evicts iBGP).
#       no_op  -> REDIST_PL permits placeholder_a /30 (adding the redistribute injects
#                 nothing of the customer /24 -> iBGP still wins via way).
#   knob=scope_redist  : PRE HAS the redistribute line; the diff EDITS REDIST_PL.
#       bypass -> placeholder_a /30 (PRE, inert) -> customer /24 (POST, injects copy).
#       no_op  -> placeholder_a /30 (PRE) -> placeholder_b /30 (POST); neither is the
#                 customer /24 -> iBGP still wins via way in BOTH snapshots.
# --------------------------------------------------------------------------- #
def _alt_pre_post(topo: _Topo) -> tuple[str, str]:
    knob, effect = topo.spec.knob, topo.spec.effect
    cust = topo.customer_prefix
    pa, pb = topo.placeholder_a, topo.placeholder_b

    if knob == "enable_redist":
        if effect == "bypass":
            pre = _alt_config(topo, redist_present=False, redist_match=cust)
            post = _alt_config(topo, redist_present=True, redist_match=cust)
        else:  # no_op
            pre = _alt_config(topo, redist_present=False, redist_match=pa)
            post = _alt_config(topo, redist_present=True, redist_match=pa)
    else:  # scope_redist
        if effect == "bypass":
            pre = _alt_config(topo, redist_present=True, redist_match=pa)
            post = _alt_config(topo, redist_present=True, redist_match=cust)
        else:  # no_op
            pre = _alt_config(topo, redist_present=True, redist_match=pa)
            post = _alt_config(topo, redist_present=True, redist_match=pb)
    return pre, post


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    alt_pre, _ = _alt_pre_post(topo)
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _way_config(topo),
        topo.name["alt"]: alt_pre,
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change: a single OSPF-namespace edit on `alt`. Zero BGP-namespace surface.
# --------------------------------------------------------------------------- #
def _apply_change(topo: _Topo) -> str:
    before, after = _alt_pre_post(topo)
    if before == after:
        raise RuntimeError(
            f"redistribute-ad change for {topo.spec.dims_label()} is a no-op patch "
            f"(pre==post on alt; seed render drift)"
        )
    return _unified(before, after, topo.name["alt"])


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
# phrased the SAME way: the prose names only WHAT OSPF-redistribution edit is made on
# `alt`, never whether the installed path / best route moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    alt = topo.name["alt"]
    asn = topo.params.core_asn
    cust = topo.customer_prefix
    pa, pb = topo.placeholder_a, topo.placeholder_b

    if knob == "enable_redist":
        scope = cust if effect == "bypass" else pa
        return (
            f"On `{alt}` (AS{asn}), under `router ospf`, add the line "
            f"`redistribute bgp route-map REDIST_CUST` (REDIST_CUST already matches "
            f"prefix-list REDIST_PL, which permits {scope}). See the diff."
        )
    else:  # scope_redist
        new = cust if effect == "bypass" else pb
        return (
            f"On `{alt}` (AS{asn}), change the network permitted by prefix-list "
            f"REDIST_PL (used by the OSPF redistribution route-map REDIST_CUST) from "
            f"{pa} to {new} (a one-line prefix-list edit). See the diff."
        )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to adjust which customer routes the "
    "interior gateway protocol carries on this path."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: RedistributeAdSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the three core loopbacks (negative controls).
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "way", "alt")] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path via alt).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host.
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint, restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"redistribute-ad quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_redistribute_ad_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    return Scenario(
        name=name,
        nodes=[src, way, alt, dst],
        pre_configs=pre,
        change_target=alt,
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
def generate_redistribute_ad_instance(
    seed: int, spec: Optional[RedistributeAdSpec] = None
) -> Scenario:
    """Emit ONE Family-1 redistribute-ad instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[RedistributeAdSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_redistribute_ad_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_redistribute_ad_suite(
    n: int, *, base_seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct
    seed per position; wrap with a fresh seed offset when ``n`` exceeds the combo
    count, giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
