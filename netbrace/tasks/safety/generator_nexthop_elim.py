"""Family-1 generator — NEXT-HOP-SELF REMOVAL / IGP-UNRESOLVABLE INVALIDATION (the
`nexthop-self-removal-invalidate` mechanism): removing the outbound next-hop rewrite on
the inspection-transiting border makes its re-advertised customer route carry the RAW
external eBGP next-hop, which is NOT carried in the IGP, so that path becomes
IGP-UNRESOLVABLE at `src` and DROPS OUT of best-path — the alternate border then wins by
ELIMINATION, silently bypassing the inspection node. ZERO new BGP attribute is set; the
diff REMOVES a single outbound next-hop-self construct on ONE border.

This is a sibling of the `igp-nh-metric-reroute` mechanism (which re-resolves an
UNCHANGED next-hop off the waypoint via an OSPF cost edit) and is structurally DISTINCT
from `lp_waypoint` (an explicit first-order LOCAL_PREF edit) and from `leak_ms` (prefix
specificity / longest-prefix match). Here the decisive change is the DISAPPEARANCE of a
recursive next-hop: the winning path is not made less-preferred, it is made INVALID
(unresolvable), and the winner flips by elimination — the only resolvable path left.

Mechanism (RFC 4271 §9.1.2.1 "a route whose NEXT_HOP is unresolvable is not considered"
+ FRR/Batfish next-hop recursive resolution through the OSPF RIB): `src` learns the
customer /24 over iBGP from BOTH `way` and `alt`. The two received paths come from the
SAME neighboring AS (the customer AS `dst`, dual-homed eBGP to both borders), so the BGP
best-path falls through LOCAL_PREF (equal, iBGP default), AS_PATH length (equal,
[AS_dst]) and ORIGIN (equal) to the MED step (RFC 4271 §9.1.2.2 step c / FRR step 6 —
MED IS compared because the first AS is the same on both paths). A STRICT baseline MED
makes `way` win:

  * PRE: `way` re-advertises the customer /24 to `src` with an OUTBOUND route-map
    `NHS_OUT` that does `set ip next-hop <way-lo>` (the Batfish-honored next-hop-self
    form — NOT bare `next-hop-self`, a documented no-op for eBGP-learned routes on the
    pinned digest). `<way-lo>` is in OSPF, so the next-hop resolves recursively through
    the OSPF RIB. `alt` does the same with `<alt-lo>`. BOTH paths are resolvable; `way`
    wins by STRICT lower MED. src->customer transits the inspection node `way`.

  * DIFF: REMOVE the next-hop-self construct on ONE border (the form is the `nhs_form`
    axis — drop the outbound APPLICATION line, or null the `set ip next-hop` LINE inside
    the route-map). The border then re-advertises the customer /24 with the RAW eBGP
    next-hop it learned from `dst` (the border<->dst link /30), which is NOT in OSPF.

  * POST (bypass — the edit is on `way`): `way`'s re-advertised next-hop is now an
    address `src` cannot resolve in the OSPF RIB, so the `way` path is INVALID
    (unresolvable, not merely less-preferred) and is removed from best-path
    consideration. `alt` is the ONLY resolvable path left, so `alt` WINS BY ELIMINATION
    despite its higher MED. src->customer now transits `alt`, bypassing `way`. The /24
    stays BEST-and-installed at src via `alt`, so it stays reachable.

THE FATAL-FLAW FIX (verified, do NOT skip): the baseline MUST make `way` win by a STRICT
MED — a step ABOVE the router-id/age tiebreak. If `way` and `alt` were tied on every BGP
attribute (so the IGP-metric or router-id step decided), Batfish would ECMP-MULTIPATH
them, D5 would fire and the pure-D4 signature would die. A strict MED gives EXACTLY ONE
best path at `src` in BOTH snapshots: `way` (MED-strict) pre, `alt` (sole-resolvable)
post. The ONLY change is the next-hop-self removal; the post winner is decided strictly
by elimination, so D5 stays empty pre and post and the oracle is byte-stable.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): removing an outbound route-map
never resets the BGP FSM (RFC 4271 §8: Established exits only on
NOTIFICATION/hold-timer/TCP teardown), so D1=∅. The /24 stays BEST-and-installed at src
(via `alt`) and at every other node, so D2=∅; `alt` delivers exactly as `way` did, so
D3=∅, D7=∅. A STRICT MED in BOTH snapshots means exactly one best path each time
(maximum-paths default 1, no equal-cost ECMP tie), so D5=∅ and the decision is made
BEFORE the nondeterministic router-id/age steps — which is what keeps it deterministic
AND keeps D5 empty.

Topology (4 nodes; OSPF underlay between src and the two borders, iBGP overlay in one
AS, eBGP to the customer AS — identical shape to the igp-metric mechanism, the KNOB
moved from the OSPF cost to the next-hop-self construct)::

      src --(OSPF /30)-- way --(eBGP /30)-- dst   (the WAY / inspection path; lower MED)
   (AS_core) |                               |
             |                               |   customer /24
             +-(OSPF /30)-- alt --(eBGP /30)-+   (originated by dst AS_dst,
                                                  dual-homed eBGP to way & alt; higher MED)

  * src, way, alt are ONE AS (iBGP, OSPF speakers). dst is a separate AS (eBGP),
    originating the customer /24 on a connected dummy host.
  * src<->way and src<->alt are OSPF point-to-point /30 links; way<->dst and alt<->dst
    are eBGP /30 links and are NOT in OSPF (this is what makes a raw eBGP next-hop
    unresolvable at src).
  * way and alt each eBGP-learn the customer /24 from dst, set a per-border MED inbound
    (way=10 STRICT-lower, alt=50), and re-advertise it to src over iBGP, rewriting the
    NEXT_HOP to their OWN loopback via the outbound `NHS_OUT` route-map. src applies NO
    BGP policy; the two paths differ ONLY in MED, so way wins strictly.

Structural axes (each a genuinely distinct config-reading task or a calibration control
— NOT a clone):

  * nhs_form ∈ {drop_apply, drop_setline} — two DIFFERENT ways to remove the next-hop
    rewrite, each a different part of the config the model must read:
      - drop_apply   : delete the outbound APPLICATION line
        `neighbor <src-lo> route-map NHS_OUT out`. The route-map block survives but is
        no longer attached, so the raw eBGP next-hop is advertised.
      - drop_setline : delete the `set ip next-hop <lo>` LINE inside the `NHS_OUT`
        route-map. The route-map stays attached but becomes a permit-all passthrough, so
        the raw eBGP next-hop is advertised. Same mechanism, a different line to read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the removal is applied to `way` (the WINNING, inspection-transiting
        border). way's path goes unresolvable -> alt wins by elimination. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of removal applied to `alt` (the ALREADY-LOSING border).
        alt's path goes unresolvable, but `way` (strict-lower MED) was already winning
        and stays resolvable, so the installed best path does not move. Ground truth is
        COMPLETELY EMPTY across ALL dimensions — the calibration trap. The prose is
        indistinguishable in style from a bypass edit.

That is 2 forms × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_igp_metric): the
core ASN, the customer-AS ASN, the loopback block, the link /30 supernet, the customer
/24, and the node base name are all drawn deterministically from the seed.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path
decision is STRICT at the MED step (way) or by sole-resolvability (alt) in both
snapshots — exactly one best path at src in each snapshot, no equal-cost ECMP tie,
maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

Public API mirrors generator_igp_metric:
    generate_nexthop_elim_suite(n, base_seed=...)        -> list[Scenario]
    generate_nexthop_elim_all_combos(seed=...)           -> list[Scenario]
    generate_nexthop_elim_instance(seed, spec=None)      -> Scenario
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
NHS_FORM_VALUES = ("drop_apply", "drop_setline")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "nhs_form": NHS_FORM_VALUES,
    "effect": EFFECT_VALUES,
}

# Per-border MED set inbound from dst. way STRICTLY lower => way wins at the MED step
# (RFC 4271 step 6, both paths from the same neighbor AS). The gap is non-equal so
# there is no ECMP tie and the decision never reaches router-id/age.
_MED_WAY = 10
_MED_ALT = 50


@dataclass(frozen=True)
class NexthopElimSpec:
    """A point in the Family-1 nexthop-elim generator space (axis tuple, pre-random)."""

    nhs_form: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.nhs_form}-{self.effect}"


def enumerate_specs() -> list[NexthopElimSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[NexthopElimSpec] = []
    for nhs_form in NHS_FORM_VALUES:
        for effect in EFFECT_VALUES:
            out.append(NexthopElimSpec(nhs_form, effect))
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
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    core_asn: int            # src/way/alt share this (iBGP)
    dst_asn: int             # the customer AS (eBGP)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string
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

    # Per-seed ROLE->POSITION swap (positional-leak fix): drawn LAST so all addressing
    # above is byte-stable; it only decides which PHYSICAL slot the waypoint role `way`
    # vs the bypass role `alt` occupies.
    swap = _rp.draw_swap(rng)

    return _Params(core_asn=core_asn, dst_asn=dst_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, name=name,
                   swap=swap)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: NexthopElimSpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: NexthopElimSpec, params: _Params) -> _Topo:
    rid_index = _rp.swapped_rid_index(
        {"src": 1, "way": 2, "alt": 3, "dst": 4}, params.swap, ("way", "alt"))
    name = _rp.swapped_names(dict(params.name), params.swap, ("way", "alt"))
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved by the (swapped) physical slot so the waypoint role's
    # link IPs also move per seed (slot-2 role uses base .0/.8, slot-3 role .4/.12).
    lo_role = "way" if rid_index["way"] == 2 else "alt"
    hi_role = "alt" if lo_role == "way" else "way"
    ip: dict[tuple[str, str], str] = {
        ("src", lo_role): addr(1), (lo_role, "src"): addr(2),
        ("src", hi_role): addr(5), (hi_role, "src"): addr(6),
        (lo_role, "dst"): addr(9), ("dst", lo_role): addr(10),
        (hi_role, "dst"): addr(13), ("dst", hi_role): addr(14),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 format). OSPF on the src<->border links + loopbacks; eBGP /30s
# are NOT in OSPF; iBGP over loopbacks; per-border inbound MED + outbound next-hop-self.
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
    """src: OSPF to way+alt, iBGP to both, NO BGP policy. The two received customer
    paths differ ONLY in MED (way strictly lower), so way wins strictly."""
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


def _egress_config(topo: _Topo, role: str, *, with_nhs: bool = True) -> str:
    """way or alt: OSPF to src, eBGP to dst (no OSPF), iBGP to src + the other border.
    Inbound `FROM_DST_IN` sets a per-border MED (way strict-lower). Outbound `NHS_OUT`
    rewrites the next-hop to the OWN loopback toward src (the Batfish-honored
    next-hop-self form). When ``with_nhs`` is False the outbound rewrite is removed (the
    raw eBGP next-hop is advertised) — used to render the POST config for that border."""
    p = topo.params
    other = "alt" if role == "way" else "way"
    lo = topo.loopback[role]
    med = _MED_WAY if role == "way" else _MED_ALT
    eth = [("eth1", f"{topo.ip[(role, 'src')]}/30"),
           ("eth2", f"{topo.ip[(role, 'dst')]}/30")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(f"interface lo\n ip address {lo}/32\n ip ospf area 0\n!\n")
    body.append(_ospf_iface("eth1", f"{topo.ip[(role, 'src')]}/30"))    # OSPF underlay
    body.append(_plain_iface("eth2", f"{topo.ip[(role, 'dst')]}/30"))  # eBGP link, no OSPF
    body.append(f"route-map FROM_DST_IN permit 10\n set metric {med}\n!\n")
    if with_nhs:
        body.append(f"route-map NHS_OUT permit 10\n set ip next-hop {lo}\n!\n")
    body.append(f"router ospf\n ospf router-id {lo}\n passive-interface lo\n!\n")
    body.append(f"router bgp {p.core_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    # iBGP to src (next-hop-self via route-map) and to the other border.
    body.append(f" neighbor {topo.loopback['src']} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback['src']} update-source lo\n")
    body.append(f" neighbor {topo.loopback[other]} remote-as {p.core_asn}\n")
    body.append(f" neighbor {topo.loopback[other]} update-source lo\n")
    # eBGP to dst (directly-connected link IP).
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.dst_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  neighbor {topo.ip[('dst', role)]} route-map FROM_DST_IN in\n")
    if with_nhs:
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
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _egress_config(topo, "way", with_nhs=True),
        topo.name["alt"]: _egress_config(topo, "alt", with_nhs=True),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change: REMOVE the next-hop-self construct on ONE border. Zero new attribute.
#   * drop_apply   : delete the outbound APPLICATION line.
#   * drop_setline : delete the `set ip next-hop` LINE inside the route-map.
# bypass edits `way` (winner -> unresolvable); no_op edits `alt` (already-losing).
# --------------------------------------------------------------------------- #
def _changed_role(spec: NexthopElimSpec) -> str:
    return "way" if spec.effect == "bypass" else "alt"


def _apply_change(topo: _Topo) -> tuple[str, str]:
    """Return (changed_node_name, unified_diff). Build POST from a controlled string
    edit and self-check it equals the corresponding render."""
    spec = topo.spec
    role = _changed_role(spec)
    node = topo.name[role]
    lo = topo.loopback[role]
    before = _egress_config(topo, role, with_nhs=True)

    if spec.nhs_form == "drop_apply":
        # Remove the outbound application line; the route-map block survives unattached.
        old = f"  neighbor {topo.loopback['src']} route-map NHS_OUT out\n"
        new = ""
        after = before.replace(old, new, 1)
    else:  # drop_setline
        # Null the `set ip next-hop` line; the route-map stays attached as permit-all.
        old = f"route-map NHS_OUT permit 10\n set ip next-hop {lo}\n!\n"
        new = "route-map NHS_OUT permit 10\n!\n"
        after = before.replace(old, new, 1)

    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {spec.dims_label()} on {node} "
            f"(seed render drift)"
        )
    if after == before:
        raise RuntimeError(f"change for {spec.dims_label()} produced no edit on {node}")
    return node, _unified(before, after, node)


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
# phrased the SAME way: the prose names only WHICH border's outbound next-hop rewrite is
# removed and HOW, never whether the recursive resolution / best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    spec = topo.spec
    role = _changed_role(spec)
    node = topo.name[role]
    if spec.nhs_form == "drop_apply":
        what = (
            "remove the outbound application of the `NHS_OUT` route-map on its iBGP "
            "session toward `{src}` (delete the `neighbor <{src}-loopback> route-map "
            "NHS_OUT out` line)"
        ).format(src=topo.name["src"])
    else:
        what = (
            "remove the `set ip next-hop` line from the `NHS_OUT` outbound route-map "
            "(leaving the route-map as a permit-all)"
        )
    return (
        f"On `{node}` (AS{topo.params.core_asn}), {what}. See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to simplify the border router's "
    "advertisement policy."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: NexthopElimSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    change_node, patch = _apply_change(topo)

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
            note=f"nexthop-elim quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_nexthop_elim_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    node_rng = random.Random(f"nexthop_elim_nodes_{seed}")
    nodes = [src, way, alt, dst]
    node_rng.shuffle(nodes)

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
def generate_nexthop_elim_instance(
    seed: int, spec: Optional[NexthopElimSpec] = None
) -> Scenario:
    """Emit ONE Family-1 nexthop-elim instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[NexthopElimSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_nexthop_elim_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_nexthop_elim_suite(
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
