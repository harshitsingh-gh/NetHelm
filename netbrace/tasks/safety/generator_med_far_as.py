"""Family-2 generator — MED-DRIVEN FAR-AS EGRESS FLIP (the `med_far_as` mechanism):
a dual-homed CUSTOMER (dst) re-tunes the per-link MED it advertises, flipping the
provider core's best path to that customer off the inspection waypoint `way` onto the
bypass `alt` — with NO change at all on the provider side and NO BGP session reset.

This is the MED member of the quiet-half catalog (Family 2, BUILD_V1.1). It is the
"the change is on the OTHER side of the eBGP boundary" sibling of `generator_lp`
(an inbound LOCAL_PREF/AS-path edit on the provider's OWN routers) and of
`generator_igp_metric` (an interior OSPF cost edit). Here the decisive edit lives on
the CUSTOMER's router (dst), one AS away, and acts through the MULTI_EXIT_DISCRIMINATOR
that dst attaches to each of its two uplinks — the textbook "customer steers the
provider's inbound traffic with MED" technique (RFC 4271 §5.1.4 / §9.1.2.1 step e).

Mechanism (RFC 4271 §9.1.2.1 step "lowest MED", FRR bgp_path_info_cmp MED step):
the customer dst is dual-homed via eBGP to BOTH provider egresses `way` and `alt`,
which are in the SAME provider AS (a single-provider dual-homing — see the HARD
CONSTRAINT below). dst originates the customer /24 and, on its OUTBOUND advertisement
to each egress, sets a per-neighbor MED (`set metric`). Within the provider AS the two
received paths to the customer /24 are otherwise IDENTICAL:

  * same LOCAL_PREF (provider applies no inbound LP policy -> default on both),
  * EQUAL AS_PATH length (both ``[AS_dst]`` — a single customer AS hop on each),
  * same ORIGIN,
so the BGP best-path decision at the inspection-source `src` FALLS THROUGH to the MED
comparison. Crucially the MED is COMPARABLE: both paths carry neighbor-AS = AS_dst (the
same first AS), so the default "compare MED only across same-neighbour-AS routes" rule
(RFC 4271 §9.1.2.1; FRR default) applies WITHOUT `always-compare-med`. And the MED dst
attached on each eBGP uplink is PRESERVED across the eBGP->iBGP boundary and propagated
on the provider's iBGP overlay (MED is non-transitive across an AS but IS carried within
the receiving AS — verified FRR docs 2026-06-15), so `src` (a provider router that learns
both paths over iBGP) compares dst's two MEDs directly.

  * PRE: dst advertises a STRICTLY LOWER MED toward `way` than toward `alt`, so the
    way-path wins the MED step and src->customer transits the inspection node `way`.
  * DIFF: dst edits ONE `set metric` value on ONE of its outbound MED route-maps
    (RAISE the MED toward way, or LOWER the MED toward alt) — framed as a routine
    customer-side inbound-TE retune. ZERO provider-side surface.
  * POST: the alt-path now has the strictly lower MED, best-path re-resolves to `alt`,
    and src->customer silently bypasses `way`.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): a MED change never resets the BGP
FSM (RFC 4271 §8: Established exits only on NOTIFICATION/hold-timer/TCP teardown), so
D1=∅. The /24 stays BEST and installed in every provider RIB (only its chosen egress
moves), so D2=∅; `alt` delivers exactly as `way` did, so D3=∅, D7=∅. A STRICT (non-equal)
MED gap in BOTH snapshots means exactly one best path each time at the MED step — which
sits ABOVE the IGP-metric and router-id steps (RFC 4271 §9.1.2.1 order) — so the
nondeterministic router-id/age tiebreak is NEVER reached, maximum-paths default 1, no
equal-cost ECMP tie, D5=∅, and the oracle is byte-identical. The provider's OSPF costs
to the two egress loopbacks are deliberately EQUAL (the MED decides first), so the IGP
step cannot covertly become the discriminator.

HARD CONSTRAINT — DUAL-HOMED, SINGLE PROVIDER (one core AS for way+alt). The honored-MED
assumption ("MED decides because both paths share the same neighbour AS") FAILS the
moment way and alt sit in DIFFERENT transit ASes: then the two paths at src carry
DIFFERENT neighbour ASes and the default rule does NOT compare their MEDs (it would need
`always-compare-med`, which Batfish does not model and which is not idiomatic for this
case). So this topology is, by construction, a single-provider dual-homing: src/way/alt
are ONE provider AS, dst is ONE customer AS dual-homed to that provider.

REQUIRED FIX (verified on the pinned Batfish digest, 2026-06-15):
  * Do NOT emit ``bgp deterministic-med`` ANYWHERE — it is unparseable in the Batfish
    snapshot (it would fail fileParseStatus). The strict MED gap in both snapshots gives
    a well-defined, order-independent best path without it.
  * Do NOT emit ``bgp always-compare-med`` either — Batfish does not model it, and the
    mechanism relies on the DEFAULT same-neighbour-AS comparison (which IS modelled).
  * The egress next-hop rewrite toward src uses the HONORED outbound route-map
    ``set ip next-hop <own-lo>`` form, NOT bare ``neighbor X next-hop-self`` (which the
    pinned digest treats as a no-op for eBGP-learned routes). Identical to
    generator_igp_metric.

Topology (4 nodes; OSPF underlay between src and the two egresses, iBGP overlay in one
provider AS, eBGP to the single customer AS)::

           MED (the KNOB) set by dst on its OUTBOUND advertisement to each egress
        +----------------------------------------------------+
        |                                                    |
      src --(OSPF /30)-- way --(eBGP /30)-- dst   (the WAY / inspection path)
   (AS_core) |                               |
             |                               |   customer /24
             +-(OSPF /30)-- alt --(eBGP /30)-+   (originated by dst AS_dst,
                                                  dual-homed eBGP to way & alt)

  * src, way, alt are ONE provider AS (iBGP full mesh over loopbacks, OSPF speakers).
    dst is the single customer AS (eBGP), originating the customer /24 on a connected
    dummy host.
  * src<->way and src<->alt are OSPF point-to-point /30 links with EQUAL cost (so the
    IGP-metric step is a tie; MED decides above it). way<->dst and alt<->dst are eBGP
    /30 links and are NOT in OSPF.
  * way and alt each eBGP-learn the customer /24 from dst (WITH dst's per-link MED) and
    re-advertise it to src over iBGP, rewriting the NEXT_HOP to their OWN loopback via
    an outbound route-map ``set ip next-hop <lo>``; the MED is carried unchanged on the
    iBGP advertisement. src resolves that loopback recursively through OSPF.
  * The provider applies NO inbound BGP policy on src; the two received paths are
    attribute-tied EXCEPT for dst's MED. The change edits ONE ``set metric`` value on
    dst — zero provider-namespace surface.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {raise_way, lower_alt} — two DIFFERENT MED edits on dst that both flip the
    egress off the waypoint, each on a different outbound route-map / opposite direction:
      - raise_way : baseline MED(dst->way)=50 < MED(dst->alt)=200 (way wins); the change
        RAISES dst's MED toward way to 300, so alt now wins (200 < 300).
      - lower_alt : same baseline; the change LOWERS dst's MED toward alt to 10, so alt
        now wins (10 < 50). Same outcome, opposite edit, different route-map to read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually flips the MED winner. D4+D10 fire; D1/D2/D3/D5/D7=∅.
        THE trap.
      - no_op  : the SAME KIND of ``set metric`` edit applied where it does NOT change
        the winner (raise the already-losing alt-side MED higher; lower the
        already-winning way-side MED lower). Ground truth is COMPLETELY EMPTY across ALL
        dimensions — the calibration trap (the model must predict an empty blast radius).
        The prose is indistinguishable in style from a bypass edit.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_igp_metric): the
core ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer
/24, and the node base name are all drawn deterministically from the seed.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path
decision is STRICT at the MED step in both snapshots (a real, non-equal MED gap) —
exactly one best path at src in each snapshot, no equal-cost ECMP tie, maximum-paths
default 1. The MED step sits above IGP-metric and router-id, so the nondeterministic
tiebreaks are never reached. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

Public API mirrors generator_igp_metric:
    generate_med_far_as_suite(n, base_seed=...)        -> list[Scenario]
    generate_med_far_as_all_combos(seed=...)           -> list[Scenario]
    generate_med_far_as_instance(seed, spec=None)      -> Scenario
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

# Baseline per-link MEDs dst advertises (way strictly lower PRE -> way wins).
_MED_WAY_PRE = 50
_MED_ALT_PRE = 200
# Post values (chosen to keep a STRICT MED gap in the post snapshot too).
_MED_WAY_RAISED = 300   # raise_way/bypass: 300 > 200 -> alt wins
_MED_ALT_LOWERED = 10   # lower_alt/bypass: 10 < 50  -> alt wins
_MED_ALT_RAISED = 400   # raise_way/no_op: 200->400, way (50) still wins (inert)
_MED_WAY_LOWERED = 5    # lower_alt/no_op: 50->5,   way still wins (inert)


@dataclass(frozen=True)
class MedFarAsSpec:
    """A point in the Family-2 med-far-as generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[MedFarAsSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[MedFarAsSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(MedFarAsSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the provider core
# (src/way/alt share one AS -> iBGP) and the customer AS (dst, eBGP). A distinct band
# from generator_igp_metric/generator_lp so generated instances never collide.
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
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

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
    spec: MedFarAsSpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: MedFarAsSpec, params: _Params) -> _Topo:
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

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 / generator_igp_metric format). OSPF on the src<->egress links +
# loopbacks (EQUAL cost, left default); eBGP /30s NOT in OSPF; iBGP over loopbacks;
# egress next-hop rewrite via the honored outbound route-map; the MED knob lives on dst.
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
    # EQUAL cost on both src<->egress links (default cost, no explicit `ip ospf cost`):
    # the IGP-metric step is a deliberate tie so the MED step decides above it.
    return (f"interface {iface}\n ip address {ipm}\n"
            " ip ospf area 0\n ip ospf network point-to-point\n!\n")


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


def _src_config(topo: _Topo) -> str:
    """src: OSPF to way+alt (EQUAL cost), iBGP to both egresses, NO BGP policy. The two
    received customer paths are attribute-tied except for dst's MED -> MED decides."""
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


def _egress_config(topo: _Topo, role: str) -> str:
    """way or alt: OSPF to src (EQUAL-cost metric link), eBGP to dst (no OSPF), iBGP to
    src + the other egress with an OUTBOUND ``set ip next-hop <own-lo>`` toward src (the
    Batfish-honored next-hop-self form). Re-advertises dst's customer /24 to src; the
    MED dst attached is carried unchanged on the iBGP advertisement (no MED policy here).
    """
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


def _dst_config(topo: _Topo, *, med_way: int, med_alt: int) -> str:
    """dst: the customer AS, eBGP to way + alt, originates the customer /24 + its lo.
    Attaches a per-neighbour OUTBOUND MED (the KNOB) via ``set metric`` route-maps.
    NEVER emits ``bgp deterministic-med`` (unparseable) nor ``always-compare-med``
    (unmodelled): the strict MED gap + default same-neighbour-AS comparison suffice."""
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
    # The two outbound MED route-maps (the KNOB). MED_TO_WAY_OUT toward `way`,
    # MED_TO_ALT_OUT toward `alt`.
    body.append(f"route-map MED_TO_WAY_OUT permit 10\n set metric {med_way}\n!\n")
    body.append(f"route-map MED_TO_ALT_OUT permit 10\n set metric {med_alt}\n!\n")
    body.append(f"router bgp {p.dst_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.core_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(f"  neighbor {topo.ip[('way', 'dst')]} route-map MED_TO_WAY_OUT out\n")
    body.append(f"  neighbor {topo.ip[('alt', 'dst')]} route-map MED_TO_ALT_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _egress_config(topo, "way"),
        topo.name["alt"]: _egress_config(topo, "alt"),
        topo.name["dst"]: _dst_config(topo, med_way=_MED_WAY_PRE, med_alt=_MED_ALT_PRE),
    }


# --------------------------------------------------------------------------- #
# The change: a single ``set metric`` edit on dst. Zero provider-namespace surface.
# --------------------------------------------------------------------------- #
def _apply_change(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    before = _dst_config(topo, med_way=_MED_WAY_PRE, med_alt=_MED_ALT_PRE)

    if knob == "raise_way":
        # bypass: raise dst->way MED 50->300 (alt's 200 now wins).
        # no_op : raise dst->alt MED 200->400 (alt was already losing; way still wins).
        if effect == "bypass":
            old = f"route-map MED_TO_WAY_OUT permit 10\n set metric {_MED_WAY_PRE}\n"
            new = f"route-map MED_TO_WAY_OUT permit 10\n set metric {_MED_WAY_RAISED}\n"
            after = _dst_config(topo, med_way=_MED_WAY_RAISED, med_alt=_MED_ALT_PRE)
        else:
            old = f"route-map MED_TO_ALT_OUT permit 10\n set metric {_MED_ALT_PRE}\n"
            new = f"route-map MED_TO_ALT_OUT permit 10\n set metric {_MED_ALT_RAISED}\n"
            after = _dst_config(topo, med_way=_MED_WAY_PRE, med_alt=_MED_ALT_RAISED)
    else:  # lower_alt
        # bypass: lower dst->alt MED 200->10 (alt now beats way's 50).
        # no_op : lower dst->way MED 50->5 (way was already winning; still wins).
        if effect == "bypass":
            old = f"route-map MED_TO_ALT_OUT permit 10\n set metric {_MED_ALT_PRE}\n"
            new = f"route-map MED_TO_ALT_OUT permit 10\n set metric {_MED_ALT_LOWERED}\n"
            after = _dst_config(topo, med_way=_MED_WAY_PRE, med_alt=_MED_ALT_LOWERED)
        else:
            old = f"route-map MED_TO_WAY_OUT permit 10\n set metric {_MED_WAY_PRE}\n"
            new = f"route-map MED_TO_WAY_OUT permit 10\n set metric {_MED_WAY_LOWERED}\n"
            after = _dst_config(topo, med_way=_MED_WAY_LOWERED, med_alt=_MED_ALT_PRE)

    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {topo.spec.dims_label()} on dst "
            f"(seed render drift)"
        )
    # Sanity: the rebuilt `after` config must equal a single in-place value swap.
    if before.replace(old, new, 1) != after:
        raise RuntimeError(
            f"change for {topo.spec.dims_label()} is not a single-line MED swap"
        )
    return _unified(before, after, topo.name["dst"])


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
# phrased the SAME way: the prose names only WHICH outbound MED route-map is edited and
# the value, never whether the best path / chosen egress moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    dst = topo.name["dst"]
    if knob == "raise_way":
        rmap = "MED_TO_WAY_OUT" if effect == "bypass" else "MED_TO_ALT_OUT"
        frm = _MED_WAY_PRE if effect == "bypass" else _MED_ALT_PRE
        to = _MED_WAY_RAISED if effect == "bypass" else _MED_ALT_RAISED
    else:  # lower_alt
        rmap = "MED_TO_ALT_OUT" if effect == "bypass" else "MED_TO_WAY_OUT"
        frm = _MED_ALT_PRE if effect == "bypass" else _MED_WAY_PRE
        to = _MED_ALT_LOWERED if effect == "bypass" else _MED_WAY_LOWERED
    return (
        f"On `{dst}` (AS{topo.params.dst_asn}), change the outbound eBGP route-map "
        f"`{rmap}` so its `set metric` value goes from {frm} to {to} (a one-line "
        f"`set metric` value edit). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tune the inbound MED the customer "
    "advertises on its uplinks for this destination."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: MedFarAsSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the three provider loopbacks (negative controls).
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
            note=f"med-far-as quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_med_far_as_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    return Scenario(
        name=name,
        nodes=[src, way, alt, dst],
        pre_configs=pre,
        change_target=dst,
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
def generate_med_far_as_instance(seed: int, spec: Optional[MedFarAsSpec] = None) -> Scenario:
    """Emit ONE Family-2 med-far-as instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[MedFarAsSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_med_far_as_all_combos(*, seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_med_far_as_suite(n: int, *, base_seed: int = 0, include_noop: bool = True) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct
    seed per position; wrap with a fresh seed offset when ``n`` exceeds the combo
    count, giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
