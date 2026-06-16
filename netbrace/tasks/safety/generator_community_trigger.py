"""Family-2 (ADVERSARIAL) generator — COMMUNITY-TRIGGERED LATENT-POLICY ABUSE (the
`community-trigger-neighbor` mechanism): a THIRD party (the foreign neighbor `dst`)
weaponizes an UNCHANGED, latent inbound community-match term on `src` to flip `src`'s
best path off the inspection waypoint — with ZERO change to `src`'s own config.

This is the adversarial sibling of the frozen quiet-half catalog (temporary/
frozen_quiet_half_scenario_set.md, Family 2). It is structurally distinct from the
Family-1 underlay-displacement mechanisms (`igp-nh-metric-reroute` and friends, where
an IGP/redistribution edit re-resolves an unchanged BGP next-hop) and from the
first-order `lp_waypoint` mechanism (an explicit LOCAL_PREF edit AT the decision point
that every model catches). Here the decisive edit lives on a DIFFERENT device than the
one whose best path moves: `src` carries a latent `match community <C> -> set
local-preference <X>` term that is INERT in the baseline (no received path carries `C`),
and the FOREIGN customer `dst` ADDITIVELY tags the advertisement it sends toward one
upstream with `C`. The tag survives `dst -> upstream -> src` and FIRES `src`'s dormant
term, re-weighting `src`'s best path off the inspection node `way` — even though `src`'s
config, and every BGP attribute the operator would diff on `dst`, looks routine.

Mechanism (RFC 1997 standard communities + RFC 4271 §9.1.1 best-path LOCAL_PREF step;
knowledge/corpus/batfish/complex_bgp_policy_patterns.md "Community-Based LOCAL_PREF
Tiers"): `src` learns the customer /24 over eBGP from BOTH upstreams (`way`, `alt`),
each next-hop DIRECTLY CONNECTED (no statics, no recursion). A strict LOCAL_PREF gap on
`src`'s inbound maps makes `way` the baseline best path (waypoint satisfied). One of
`src`'s inbound maps carries a LATENT community-match term (a real de-pref / promote
policy an operator left in place "for emergencies"); no baseline path matches it. The
change is on `dst`: it attaches `set community <C> additive` to its outbound
advertisement toward ONE upstream. The tag rides the customer route to `src` and trips
the dormant term, flipping the LOCAL_PREF gap so the OTHER upstream now wins.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): a community tag never resets a BGP
session (RFC 4271 §8: Established exits only on NOTIFICATION/hold-timer/TCP teardown),
so D1=∅. The /24 stays BEST and installed in every RIB (only the chosen upstream moves),
so D2=∅; the bypass upstream delivers exactly as `way` did, so D3=∅, D7=∅. A STRICT
(non-equal) LOCAL_PREF gap in BOTH snapshots means exactly one best path each time
(maximum-paths default 1, no equal-cost ECMP tie), so D5=∅ and the oracle is
byte-identical. The strict LP gap is decided at the LOCAL_PREF step BEFORE the
nondeterministic router-id/age steps are reached (the documented Batfish ECMP-multipath
trap), which is what makes it deterministic AND keeps D5 empty. The whole point: the
weaponized device is NOT the device that changes, so a reviewer diffing `dst`'s routine
"tag our routes for the upstream" edit sees nothing — the damage is latent in `src`.

Topology (4 nodes, ALL eBGP, distinct ASNs, directly-connected next-hops)::

         inbound route-map with a LATENT community-match term on src
      +----------------------------------------------------+
      |                                                    |
    src ---/30--- way (AS_way) ---/30(eBGP)--- dst   (the WAY / inspection path)
 (AS_src) |                                      |
          |                                      |   customer /24
          +---/30--- alt (AS_alt) ---/30(eBGP)---+   (originated by dst, dual-homed
                                                     eBGP to way & alt; THE CHANGE
                                                     TARGET — it tags one advertisement)

  * src is AS_src; it eBGP-peers DIRECTLY (over the /30 link IP) with both way (AS_way)
    and alt (AS_alt). No update-source, no multihop, no statics, no recursion.
  * way and alt are distinct upstream ASes; each eBGP-peers with dst (AS_dst) over a
    directly-connected /30 and re-advertises the customer /24 to src, carrying the
    community community through (each upstream has `send-community` toward src).
  * dst originates the customer /24 on a dummy host and eBGP-peers with BOTH upstreams
    (each with `send-community`). dst is the CHANGE TARGET: the diff attaches an
    outbound `set community <C> additive` route-map to ONE of dst's upstream sessions.
  * src applies an INBOUND route-map per upstream. Exactly ONE of them carries the
    latent `match community <C> -> set local-preference <X>` term (dormant in baseline).

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {depref_way, prefer_alt} — two OPPOSITE latent-policy shapes, each on a
    different src inbound map and decided in the opposite LOCAL_PREF direction:
      - depref_way : the latent term lives on src's WAY inbound map and LOWERS the
        matched path (`match community C -> set local-preference 50`); a fall-through
        term sets the baseline way LP 200 > alt 100. The change tags the WAY path, so
        way drops to 50 and alt's 100 wins. Reader must parse a community DE-PREF on
        the inspection-side map.
      - prefer_alt : the latent term lives on src's ALT inbound map and RAISES the
        matched path (`match community C -> set local-preference 300`); baseline way LP
        200 > alt fall-through 100. The change tags the ALT path, so alt jumps to 300
        and beats way's 200. Same D4 outcome class, OPPOSITE edit, the latent term on
        the OTHER map and in the OTHER LP direction.

  * effect ∈ {bypass, no_op} — the calibration axis (the SAME kind of dst edit, applied
    where it does/does not move src's installed best path):
      - bypass : dst tags the upstream whose src-inbound map carries the matching term
        (way for depref_way, alt for prefer_alt). The tag trips the latent term and the
        LOCAL_PREF gap flips. D4+D10 fire; D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : dst tags the OTHER upstream — the one whose src-inbound map has NO
        community-match term — so the identical `set community C additive` edit is
        INERT and the baseline best path is unchanged. Ground truth is COMPLETELY EMPTY
        across ALL dimensions (the model must predict an empty blast radius). The prose
        is indistinguishable in style from a bypass edit; only tracing the community
        from dst's tagged neighbor through to src's matching map separates them.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): the FOUR
distinct ASNs (src/way/alt/dst), the loopback block, the link /30 supernet, the customer
/24, the node base name, AND the trigger community value are all drawn deterministically
from the seed. Same seed ⇒ byte-identical instance; different seed ⇒ a novel instance.

Determinism contract (oracle_determinism_spec_v1.md class STATIC-DET): every best-path
decision is STRICT at the LOCAL_PREF step in both snapshots (a real, non-equal LP gap:
200 vs 100 baseline; 100 vs 50 or 300 vs 200 post) — exactly one best path at src in
each snapshot, no equal-cost ECMP tie, maximum-paths default 1. D4 is scored by
ExtendedOracle._waypoint_diff as the all-traces-transit invariant; D10 by the matching
kind="waypoint" IntentInvariant. NO static routes ⇒ no recursive-next-hop artifact.

Mechanism VERIFIED LIVE on the pinned batfish/allinone:nethelm digest (2026-06-15):
both knobs flip src's best path off `way` in bypass and stay on `way` in no_op; the
standard-community machinery (`bgp community-list standard`, `match community`,
`set community <C> additive`, `send-community`) parses clean (CUMULUS_CONCATENATED,
zero init issues) and is honored across the eBGP hops. (Large/extended communities are
NOT in the Batfish FRR grammar — `rmm_large_community`/`rmm_extcommunity` are commented
out — so only STANDARD communities are used.)

Public API mirrors generator_lp:
    generate_community_trigger_suite(n, base_seed=...)        -> list[Scenario]
    generate_community_trigger_all_combos(seed=...)           -> list[Scenario]
    generate_community_trigger_instance(seed, spec=None)      -> Scenario
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
KNOB_VALUES = ("depref_way", "prefer_alt")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# LOCAL_PREF tiers (strict gaps in BOTH snapshots — the determinism contract).
#   depref_way: way fall-through 200 > alt 100 (PRE); way-matched 50 < alt 100 (POST).
#   prefer_alt: way 200 > alt fall-through 100 (PRE); alt-matched 300 > way 200 (POST).
_LP_WAY_BASE = 200      # depref_way: way's fall-through (baseline winner)
_LP_ALT_BASE = 100      # depref_way: alt's flat LP (baseline loser)
_LP_WAY_DEPREF = 50     # depref_way: the latent de-pref value on the way map (matched)
_LP_WAY_FLAT = 200      # prefer_alt: way's flat LP (baseline winner)
_LP_ALT_FALLTHRU = 100  # prefer_alt: alt's fall-through (baseline loser)
_LP_ALT_PROMOTE = 300   # prefer_alt: the latent promote value on the alt map (matched)


@dataclass(frozen=True)
class CommunityTriggerSpec:
    """A point in the Family-2 community-trigger generator space (axis tuple)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[CommunityTriggerSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[CommunityTriggerSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(CommunityTriggerSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). FOUR DISTINCT ASNs (src/way/alt/dst). A distinct
# sub-block from the other generators so a generated instance never collides.
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

    asn: dict[str, int]      # role -> ASN  (roles: src, way, alt, dst)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string
    community: str           # the trigger standard community, e.g. "64512:837"


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    # Four DISTINCT ASNs, one per role.
    asns: list[int] = []
    while len(asns) < 4:
        a = rng.randint(_ASN_LO, _ASN_HI)
        if a not in asns:
            asns.append(a)
    asn = dict(zip(_ROLES, asns))

    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    # Trigger community: a randomized 16:16 standard community (RFC 1997) in the private
    # AS-prefix range so it never collides with a real AS's community policy. Kept clear
    # of the well-known reserved set (no-export 65535:65281 etc.).
    community = f"{rng.randint(64512, 65534)}:{rng.randint(1, 65000)}"

    return _Params(asn=asn, loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name=name, community=community)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    """A concrete, addressed all-eBGP topology for one instance."""

    params: _Params
    spec: CommunityTriggerSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: CommunityTriggerSpec, params: _Params) -> _Topo:
    name = dict(params.name)
    rid_index = {"src": 1, "way": 2, "alt": 3, "dst": 4}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved from the link block:
    #   src-way base .0  (src=.1, way=.2)
    #   src-alt base .4  (src=.5, alt=.6)
    #   way-dst base .8  (way=.9, dst=.10)
    #   alt-dst base .12 (alt=.13, dst=.14)
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
# Config text rendering (FRR / CUMULUS_CONCATENATED, the verified leak_ms/lp format).
# All eBGP, directly-connected /30 peers, NO static routes anywhere.
# --------------------------------------------------------------------------- #
_LINK_MASK = "/30"


def _ifaces_intf_text(
    node_name: str, loopback: str,
    eth_ifaces: list[tuple[str, str]],   # (iface, "ip/mask")
    dummies: list[tuple[str, str]],      # (iface, "ip/mask")
) -> tuple[str, str]:
    """Return (interfaces-stanza-block, frr-interface-stanza-block) for a node."""
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


# ---- src's inbound steering maps (the LATENT community-match term lives here) ----- #
# The baseline always makes `way` the strict LOCAL_PREF winner. The latent term is
# INERT in the baseline (no received path carries the community); it is the SAME text in
# both snapshots (src never changes). Which map carries the latent term depends on knob.
def _src_inbound_maps(topo: _Topo) -> tuple[list[str], list[str]]:
    """Return (RM_UPLINK1_IN lines (toward way), RM_UPLINK2_IN lines (toward alt))."""
    knob = topo.spec.knob
    if knob == "depref_way":
        # Latent DE-PREF on the way map: a matched path drops to LP 50; the fall-through
        # term sets the baseline way LP 200 (> alt's flat 100).
        way = [
            "route-map RM_UPLINK1_IN permit 10",
            " match community CL_TRIGGER",
            f" set local-preference {_LP_WAY_DEPREF}",
            "!",
            "route-map RM_UPLINK1_IN permit 20",
            f" set local-preference {_LP_WAY_BASE}",
            "!",
        ]
        alt = [
            "route-map RM_UPLINK2_IN permit 10",
            f" set local-preference {_LP_ALT_BASE}",
            "!",
        ]
    else:  # prefer_alt
        # Latent PROMOTE on the alt map: a matched path jumps to LP 300; the fall-through
        # term sets the baseline alt LP 100 (< way's flat 200).
        way = [
            "route-map RM_UPLINK1_IN permit 10",
            f" set local-preference {_LP_WAY_FLAT}",
            "!",
        ]
        alt = [
            "route-map RM_UPLINK2_IN permit 10",
            " match community CL_TRIGGER",
            f" set local-preference {_LP_ALT_PROMOTE}",
            "!",
            "route-map RM_UPLINK2_IN permit 20",
            f" set local-preference {_LP_ALT_FALLTHRU}",
            "!",
        ]
    return way, alt


def _src_config(topo: _Topo) -> str:
    """src: eBGP to way+alt over directly-connected /30s. A latent community-list +
    inbound community-match term (dormant in baseline). NO change is ever made here."""
    p = topo.params
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name["src"], topo.loopback["src"], eth, [])
    way_map, alt_map = _src_inbound_maps(topo)

    body = [ib, _frr_header(topo.name["src"]), fb]
    # The community-list the latent term references (RFC 1997 standard community).
    body.append(f"bgp community-list standard CL_TRIGGER permit {p.community}\n!\n")
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
    """way or alt: eBGP to src and to dst, NO policy, NO statics. `send-community`
    toward src so any community dst tags survives the dst->upstream->src path."""
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
    body.append(f"  neighbor {topo.ip[('src', role)]} send-community\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo, *, tag_target: Optional[str]) -> str:
    """dst: the customer AS, eBGP to way + alt, originates the customer /24. The CHANGE
    TARGET. ``tag_target`` in {None, "way", "alt"} selects which upstream session (if
    any) gets the outbound `set community <C> additive` route-map. Both sessions carry
    `send-community` so a tagged community is actually advertised."""
    p = topo.params
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    ib, fb = _ifaces_intf_text(topo.name["dst"], topo.loopback["dst"], eth, dummies)
    body = [ib, _frr_header(topo.name["dst"]), fb]
    if tag_target is not None:
        body.append(f"route-map RM_TAG_OUT permit 10\n set community {p.community} additive\n!\n")
    body.append(f"router bgp {p.asn['dst']}\n")
    body.append(f" bgp router-id {topo.loopback['dst']}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback['dst']}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(f"  neighbor {topo.ip[('way', 'dst')]} send-community\n")
    body.append(f"  neighbor {topo.ip[('alt', 'dst')]} send-community\n")
    if tag_target == "way":
        body.append(f"  neighbor {topo.ip[('way', 'dst')]} route-map RM_TAG_OUT out\n")
    elif tag_target == "alt":
        body.append(f"  neighbor {topo.ip[('alt', 'dst')]} route-map RM_TAG_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _upstream_config(topo, "way"),
        topo.name["alt"]: _upstream_config(topo, "alt"),
        # Baseline dst tags NOTHING (the latent term is dormant).
        topo.name["dst"]: _dst_config(topo, tag_target=None),
    }


# --------------------------------------------------------------------------- #
# The change (an OUTBOUND community-tag edit on dst — the third party). The TRIGGERED
# upstream depends on the knob; the no_op tags the OTHER upstream (inert at src).
#   depref_way: matching term is on src's WAY map  -> bypass tags way, no_op tags alt.
#   prefer_alt: matching term is on src's ALT map  -> bypass tags alt, no_op tags way.
# --------------------------------------------------------------------------- #
def _triggered_upstream(knob: str) -> str:
    """The upstream whose src-inbound map carries the community-match term."""
    return "way" if knob == "depref_way" else "alt"


def _tag_target(spec: CommunityTriggerSpec) -> str:
    triggered = _triggered_upstream(spec.knob)
    other = "alt" if triggered == "way" else "way"
    return triggered if spec.effect == "bypass" else other


def _apply_change(topo: _Topo) -> str:
    """Return the unified diff applied to dst for this (knob, effect)."""
    before = _dst_config(topo, tag_target=None)
    after = _dst_config(topo, tag_target=_tag_target(topo.spec))
    if before == after:
        raise RuntimeError(
            f"change produced no diff for {topo.spec.dims_label()} on dst "
            f"(seed render drift)"
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
# phrased the SAME way: the prose names only WHICH of dst's upstream sessions gets the
# `set community ... additive` tag, never whether src's best path moves. "community" and
# "additive" name the edited construct (allowed); "bypass/reroute/wins/best path" do not
# appear anywhere. The latent term on src is visible in the per-node configs the model
# reads — the trap is whether the model traces the community to it.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    p = topo.params
    dst = topo.name["dst"]
    tagged = topo.name[_tag_target(topo.spec)]
    return (
        f"On `{dst}` (AS{p.asn['dst']}), attach an outbound route-map (RM_TAG_OUT) to "
        f"its eBGP session toward `{tagged}` that adds the standard community "
        f"{p.community} to advertised routes (`set community {p.community} additive`; "
        f"the session already carries `send-community`). A one-line tag on one "
        f"upstream session. See the diff and the per-node configs."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tag the customer's routes with a "
    "community for this upstream."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: CommunityTriggerSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: all loopbacks (negative controls) + customer /24.
    watched = [f"{topo.loopback[r]}/32" for r in _ROLES] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host so the
    # trace has a real connected accept at dst (the bare .0 is not a host).
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint, restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"community-trigger quiet reroute: src->{cust} must transit {way}; a "
                 f"third party (dst) tags one upstream to trip src's latent term.",
        )
    ]

    name = f"gen_community_trigger_{spec.dims_label()}_s{seed}"
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
# Public API (mirrors generator_lp).
# --------------------------------------------------------------------------- #
def generate_community_trigger_instance(
    seed: int, spec: Optional[CommunityTriggerSpec] = None
) -> Scenario:
    """Emit ONE Family-2 community-trigger instance. With ``spec=None`` the axis tuple
    is chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[CommunityTriggerSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_community_trigger_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_community_trigger_suite(
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
