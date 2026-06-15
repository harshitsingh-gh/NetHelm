"""Family-2 generator — ROUTE-MAP CLAUSE FALL-THROUGH (the `clause_fallthrough`
mechanism, subtraction axis / BUILD_V1.1): a structural DELETE / RE-SEQUENCE of a
route-map clause — no VALUE edit — drops the inspection path's LOCAL_PREF onto a
lower catch-all clause, flipping the best path off the waypoint while the catch-all
keeps the prefix PERMITTED (so D2 stays empty).

This is the SUBTRACTION sibling of the Family-1 `lp_waypoint` value-edit mechanism
(generator_lp.py, the `lp_drop_way` knob). There, the operator LOWERS a
`set local-preference` value; a model that reads the new number can solve it by
arithmetic. HERE the LOCAL_PREF numbers never change — the operator removes (or
re-sequences below the catch-all) the EARLY high-LP clause, so the way-path stops
first-matching it and FALLS THROUGH to a lower-LP permit clause it shares with the
alt-path. The decisive fact is route-map *clause ordering / first-match* semantics
(FRR route-map = ordered list, processing STOPS at the first matching permit term —
docs.frrouting.org/en/latest/routemap.html), not a value. A model that only diffs
the numeric `set` values sees nothing and mis-predicts an empty blast radius; a
model that reasons about which clause the way-path now first-matches catches it.

Mechanism (RFC 4271 §9.1.2.2 step 2 LOCAL_PREF, then step 4 AS_PATH length; the
community/as-path-tier first-match idiom from knowledge/corpus/batfish/
complex_bgp_policy_patterns.md "Community-Based LOCAL_PREF Tiers"): `src` is
dual-homed (all-eBGP, directly-connected /30 next-hops, NO statics) to the
inspection upstream `way` and the bypass upstream `alt`; both eBGP-peer with the
customer AS `dst`, which originates the customer /24. `src` applies ONE SHARED
inbound route-map (`RM_UPLINK_IN`) to BOTH upstream sessions:

    bgp as-path access-list AS_WAY permit ^<way_asn>_      (the way-path discriminator)
    route-map RM_UPLINK_IN permit 10  match as-path AS_WAY  set local-preference 300
    route-map RM_UPLINK_IN permit 20  set local-preference 100   (the catch-all)

  * PRE: the way-path (its AS_PATH begins with way's ASN) FIRST-MATCHES clause 10 ->
    LOCAL_PREF 300; the alt-path skips clause 10 (its AS_PATH begins with alt) and
    matches the catch-all clause 20 -> LOCAL_PREF 100. 300 > 100 so `way` wins and
    src->customer transits the inspection node `way`.
  * DIFF (bypass): DELETE or RE-SEQUENCE clause 10 (NO value edit). The way-path now
    first-matches the catch-all clause 20 -> LOCAL_PREF 100, tying alt's 100.
  * POST: with LOCAL_PREF tied at 100, best-path falls through to AS_PATH length
    (RFC 4271 step 4). The customer AS `dst` prepends its OWN ASN once toward `way`
    (a baseline outbound TE knob on dst), so the way-path AS_PATH ([way,dst,dst],
    len 3) is STRICTLY longer than the alt-path ([alt,dst], len 2) -> `alt` wins and
    src->customer silently bypasses `way`.

The catch-all clause 20 is a PERMIT (empty match), so the way-path is never dropped
— it is merely re-weighted. That makes the proposal's "the catch-all prevents a
loud D2 withdrawal" TRUE BY CONSTRUCTION: the prefix stays in every RIB (D2=∅),
`alt` delivers exactly as `way` did (D3=∅, D7=∅), and an eBGP attribute change never
resets the FSM (D1=∅, RFC 4271 §8). A STRICT discriminator sits at a step ABOVE
router-id in BOTH snapshots (LOCAL_PREF gap 300>100 pre; AS_PATH-length gap 3>2
post), so there is exactly one best path each time — no equal-cost ECMP tie, so D5=∅
and the oracle is byte-identical (the documented Batfish ECMP-multipath router-id
trap is never reached). ONLY D4 (waypoint) + D10 (intent) fire.

Topology (4 nodes, ALL eBGP, distinct ASNs, directly-connected next-hops)::

           ONE shared inbound route-map (the KNOB) on src toward BOTH upstreams
        +-----------------------------------------------------------+
        |                                                           |
      src ---/30--- way (AS_way) ---/30(eBGP)--- dst   (the WAY / inspection path)
   (AS_src) |                                      |
            |                                      |   customer /24 (originated by
            +---/30--- alt (AS_alt) ---/30(eBGP)---+   dst; dst prepends its own ASN
                                                       once OUTBOUND toward `way`)

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * edit ∈ {delete, resequence} — the TWO structural ways to make the way-path stop
    first-matching the high-LP clause, with ZERO value edit:
      - delete     : remove the `permit 10` block entirely -> way-path falls to the
        catch-all. The reader must notice an absent clause.
      - resequence : move the `permit 10` block to `permit 30` (BELOW the catch-all
        `permit 20`). The clause still EXISTS but is now unreachable for the way-path
        (FRR stops at the first matching permit), so it falls to the catch-all. The
        reader must reason about clause ORDER, not presence — a strictly harder
        config-reading task than a deletion, same ground truth.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit is applied to the LIVE high-LP clause (`permit 10`), so the
        way-path's first-match actually moves to the catch-all. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of structural edit (delete/re-sequence a clause) is
        applied to an INERT decoy clause (`permit 5`, which matches an AS_PATH list
        for a SENTINEL ASN that no route in the topology carries). The way-path never
        first-matched the decoy, so removing/moving it changes NOTHING — the way-path
        still first-matches the live `permit 10`. Ground truth is COMPLETELY EMPTY
        across ALL dimensions — the calibration trap (the model must predict an empty
        blast radius). The prose is indistinguishable in style from a bypass edit;
        only reasoning about WHICH clause the way-path first-matches separates them.

That is 2 edits × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): FIVE
distinct ASNs (src/way/alt/dst + a sentinel), the loopback block, the link /30
supernet, the customer /24, the route-map/as-path-list names, and the node base name
are all drawn deterministically from the seed. Same seed ⇒ byte-identical instance;
different seed ⇒ a novel instance even for this public mechanism.

Determinism contract (oracle_determinism_spec_v1.md, STATIC-DET): every best-path
decision is STRICT in both snapshots (LOCAL_PREF gap pre, AS_PATH-length gap post) —
exactly one best path at src each time, no equal-cost ECMP tie, maximum-paths default
1. NO static routes (all-eBGP, directly-connected next-hops) ⇒ no recursive-next-hop
artifact. D4 is scored by ExtendedOracle._waypoint_diff (all-traces-transit), D10 by
the matching kind="waypoint" IntentInvariant.

Public API mirrors generator_lp:
    generate_clause_fallthrough_suite(n, base_seed=...)        -> list[Scenario]
    generate_clause_fallthrough_all_combos(seed=...)           -> list[Scenario]
    generate_clause_fallthrough_instance(seed, spec=None)      -> Scenario
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
EDIT_VALUES = ("delete", "resequence")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "edit": EDIT_VALUES,
    "effect": EFFECT_VALUES,
}

# LOCAL_PREF tiers. The HIGH tier (way-path first-match) strictly beats the catch-all
# tier in the PRE state; the numbers NEVER change across the diff (subtraction axis).
_LP_HIGH = 300
_LP_CATCHALL = 100


@dataclass(frozen=True)
class ClauseFallthroughSpec:
    """A point in the Family-2 clause-fallthrough generator space (axis tuple)."""

    edit: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.edit}-{self.effect}"


def enumerate_specs() -> list[ClauseFallthroughSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[ClauseFallthroughSpec] = []
    for edit in EDIT_VALUES:
        for effect in EFFECT_VALUES:
            out.append(ClauseFallthroughSpec(edit, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). FIVE DISTINCT ASNs: src/way/alt/dst plus a
# SENTINEL ASN used only by the inert decoy clause's as-path list (no route carries
# it). Kept clear of the hand-authored 65000 family and the other generators' bands.
_ASN_LO, _ASN_HI = 4_200_400_000, 4_200_499_999

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
    sentinel_asn: int        # the decoy as-path list's ASN (no route carries it)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string
    rm_name: str             # the shared inbound route-map name
    asl_way: str             # the way-path as-path access-list name
    asl_sentinel: str        # the decoy as-path access-list name


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    # Four DISTINCT role ASNs + a fifth distinct sentinel ASN.
    asns: list[int] = []
    while len(asns) < 5:
        a = rng.randint(_ASN_LO, _ASN_HI)
        if a not in asns:
            asns.append(a)
    asn = dict(zip(_ROLES, asns[:4]))
    sentinel_asn = asns[4]

    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    # Randomize the policy-object names too (contamination control: even the
    # route-map / as-path-list identifiers differ per seed).
    tag = rng.randint(1000, 9999)
    rm_name = f"RM_UPLINK_IN_{tag}"
    asl_way = f"AS_WAY_{tag}"
    asl_sentinel = f"AS_SENT_{tag}"

    return _Params(
        asn=asn, sentinel_asn=sentinel_asn, loop_block=loop_block,
        link_block=link_block, customer_net=customer_net, name=name,
        rm_name=rm_name, asl_way=asl_way, asl_sentinel=asl_sentinel,
    )


# --------------------------------------------------------------------------- #
# Topology builder: src dual-homed (eBGP) to way + alt, each eBGP to dst.
# Links, fixed order (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    """A concrete, addressed all-eBGP topology for one instance."""

    params: _Params
    spec: ClauseFallthroughSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: ClauseFallthroughSpec, params: _Params) -> _Topo:
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
# Config text rendering (FRR / CUMULUS_CONCATENATED, the verified leak_ms format).
# All eBGP, directly-connected /30 peers, NO static routes anywhere.
# --------------------------------------------------------------------------- #
_LINK_MASK = "/30"


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
        "frr version 10.6.1\n"
        "frr defaults traditional\n"
        f"hostname {node_name}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


# ---- the SHARED inbound route-map on src (the KNOB lives here) -------------- #
# The PRE-state route-map text. Two as-path access-lists (the live way discriminator
# and an inert sentinel decoy) plus a three-clause route-map:
#   permit 5  match AS_SENTINEL  set LP 300   (decoy: matches a sentinel ASN nothing
#                                              carries; touched only by the no_op edit)
#   permit 10 match AS_WAY       set LP 300   (the LIVE high-LP clause; touched by bypass)
#   permit 20                    set LP 100   (the catch-all PERMIT — keeps D2 empty)
def _src_rmap_block(topo: _Topo) -> str:
    p = topo.params
    # AS_PATH regex form (VERIFIED on the pinned digest, 2026-06-15): Batfish's FRR
    # model does NOT treat the trailing `_` separator as matching the space between a
    # long 4-byte ASN and the next AS, so `^<asn>_` FAILS to match `[<asn>, <next>...]`
    # (it falls through to the catch-all). The verified, precise form is
    # `^<asn> ` (caret + ASN + a literal space): it anchors `<asn>` as the FIRST AS
    # and requires at least one following AS. The way-path here is always
    # `[way, dst, dst]` (>=2 ASes) so the trailing space always exists; the sentinel
    # list uses the same form for symmetry (it matches nothing because no route in
    # the topology begins with the sentinel ASN).
    lines = [
        f"bgp as-path access-list {p.asl_sentinel} permit ^{p.sentinel_asn} ",
        f"bgp as-path access-list {p.asl_way} permit ^{p.asn['way']} ",
        "!",
        f"route-map {p.rm_name} permit 5",
        f" match as-path {p.asl_sentinel}",
        f" set local-preference {_LP_HIGH}",
        f"route-map {p.rm_name} permit 10",
        f" match as-path {p.asl_way}",
        f" set local-preference {_LP_HIGH}",
        f"route-map {p.rm_name} permit 20",
        f" set local-preference {_LP_CATCHALL}",
        "!",
    ]
    return "\n".join(lines) + "\n"


def _src_config(topo: _Topo) -> str:
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}"))
    body.append(_src_rmap_block(topo))
    body.append(f"router bgp {p.asn['src']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    # ONE shared inbound route-map on BOTH upstream sessions (the mechanism).
    body.append(f"  neighbor {topo.ip[('way', 'src')]} route-map {p.rm_name} in\n")
    body.append(f"  neighbor {topo.ip[('alt', 'src')]} route-map {p.rm_name} in\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _way_config(topo: _Topo) -> str:
    """way (inspection upstream): eBGP to src and to dst, no policy, no statics."""
    p = topo.params
    lo = topo.loopback["way"]
    eth = [("eth1", f"{topo.ip[('way', 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('way', 'dst')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["way"], lo, eth, []), _frr_header(topo.name["way"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('way', 'src')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('way', 'dst')]}{_LINK_MASK}"))
    body.append(f"router bgp {p.asn['way']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('src', 'way')]} remote-as {p.asn['src']}\n")
    body.append(f" neighbor {topo.ip[('dst', 'way')]} remote-as {p.asn['dst']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _alt_config(topo: _Topo) -> str:
    """alt (bypass upstream): eBGP to src and to dst, no policy, no statics."""
    p = topo.params
    lo = topo.loopback["alt"]
    eth = [("eth1", f"{topo.ip[('alt', 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('alt', 'dst')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["alt"], lo, eth, []), _frr_header(topo.name["alt"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('alt', 'src')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('alt', 'dst')]}{_LINK_MASK}"))
    body.append(f"router bgp {p.asn['alt']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('src', 'alt')]} remote-as {p.asn['src']}\n")
    body.append(f" neighbor {topo.ip[('dst', 'alt')]} remote-as {p.asn['dst']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo) -> str:
    """dst (customer AS): eBGP to way + alt, originates the customer /24 + its lo.

    Baseline TE knob: dst prepends its OWN ASN once OUTBOUND toward `way`, so the
    way-path AS_PATH ([way,dst,dst], len 3) is STRICTLY longer than the alt-path
    ([alt,dst], len 2). In PRE this is overridden by LOCAL_PREF (300 vs 100); in
    POST, with LOCAL_PREF tied at 100, it is the strict best-path discriminator
    (RFC 4271 step 4) that keeps the decision ABOVE the router-id tiebreak.
    """
    p = topo.params
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["dst"], lo, eth, dummies), _frr_header(topo.name["dst"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}"))
    body.append(f"interface dum0\n ip address {topo.customer_ip}/24\n!\n")
    # Outbound prepend toward `way` only (literal-ASN syntax, Batfish-parseable).
    body.append(f"route-map TO_WAY_OUT permit 10\n set as-path prepend {p.asn['dst']}\n!\n")
    body.append(f"router bgp {p.asn['dst']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(f"  neighbor {topo.ip[('way', 'dst')]} route-map TO_WAY_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _way_config(topo),
        topo.name["alt"]: _alt_config(topo),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change: a STRUCTURAL delete / re-sequence of a route-map clause on src.
# NO value edit (the LOCAL_PREF numbers are byte-stable across the diff).
# --------------------------------------------------------------------------- #
def _clause_block(rm: str, seq: int, match_line: str, lp: int) -> str:
    """Render one full route-map clause block (the unit we delete / re-sequence)."""
    return (
        f"route-map {rm} permit {seq}\n"
        f" {match_line}\n"
        f" set local-preference {lp}\n"
    )


def _apply_change(topo: _Topo) -> str:
    edit, effect = topo.spec.edit, topo.spec.effect
    p = topo.params
    before = _src_config(topo)

    live_match = f"match as-path {p.asl_way}"        # clause 10 (way discriminator)
    decoy_match = f"match as-path {p.asl_sentinel}"  # clause 5  (inert sentinel)

    if effect == "bypass":
        # Touch the LIVE high-LP clause (permit 10) -> way-path first-match moves to
        # the catch-all (permit 20) -> LP drops to the catch-all tier.
        target_seq, target_match = 10, live_match
    else:
        # Touch the INERT decoy clause (permit 5) -> way-path first-match unchanged
        # (it never matched the decoy) -> empty ground truth.
        target_seq, target_match = 5, decoy_match

    old_block = _clause_block(p.rm_name, target_seq, target_match, _LP_HIGH)

    if edit == "delete":
        # Remove the clause block entirely.
        new_block = ""
    else:  # resequence: move the SAME clause to permit 30 (below the catch-all 20).
        new_block = _clause_block(p.rm_name, 30, target_match, _LP_HIGH)

    if old_block not in before:
        raise RuntimeError(
            f"change anchor not found for {topo.spec.dims_label()} on src "
            f"(seed render drift)"
        )

    if edit == "delete":
        after = before.replace(old_block, new_block, 1)
    else:
        # Re-sequence = remove from its original position and append the moved block
        # immediately AFTER the catch-all clause's terminating '!' so it lands below
        # permit 20 in numeric order. We anchor on the catch-all clause + its '!'.
        removed = before.replace(old_block, "", 1)
        catchall = _clause_block(p.rm_name, 20, "", _LP_CATCHALL)
        # The catch-all has an empty match line -> its block is rendered WITHOUT a
        # match line. Build the real catch-all text (no match) for the anchor.
        catchall = (
            f"route-map {p.rm_name} permit 20\n"
            f" set local-preference {_LP_CATCHALL}\n"
        )
        anchor = catchall + "!\n"
        if anchor not in removed:
            raise RuntimeError(
                f"resequence anchor not found for {topo.spec.dims_label()} on src"
            )
        after = removed.replace(anchor, catchall + new_block + "!\n", 1)

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
# phrased the SAME way: the prose names only WHICH clause is removed / re-sequenced,
# never whether the best path moves. This is the prompt-hygiene gate; "falls through",
# "alt becomes preferred", "bypass", "nothing changes" are ALL leaks and appear
# NOWHERE. Route-map / clause / sequence are config-construct words (allowed).
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    edit, effect = topo.spec.edit, topo.spec.effect
    p = topo.params
    seq = 10 if effect == "bypass" else 5
    if edit == "delete":
        return (
            f"On `{topo.name['src']}` (AS{p.asn['src']}), remove clause "
            f"`permit {seq}` from the inbound eBGP route-map `{p.rm_name}` (a "
            f"one-clause deletion). See the diff."
        )
    return (
        f"On `{topo.name['src']}` (AS{p.asn['src']}), re-sequence clause "
        f"`permit {seq}` of the inbound eBGP route-map `{p.rm_name}` to `permit 30` "
        f"(a clause re-sequence). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tidy the inbound route-map applied "
    "to the upstream sessions for this destination."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: ClauseFallthroughSpec, seed: int) -> Scenario:
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

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host so the
    # trace has a real connected accept at dst (the bare .0 is not a host).
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint, restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"clause-fallthrough quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_clause_fallthrough_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    return Scenario(
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
        intent_invariants=intent_invariants,
        # bypass = the trap (D4+D10 fire while sessions/prefixes/reachability survive);
        # no_op  = genuinely inert (empty GT), so is_trap stays False.
        is_trap=(spec.effect == "bypass"),
        provenance="templated",
    )


# --------------------------------------------------------------------------- #
# Public API (mirrors generator_lp).
# --------------------------------------------------------------------------- #
def generate_clause_fallthrough_instance(
    seed: int, spec: Optional[ClauseFallthroughSpec] = None
) -> Scenario:
    """Emit ONE Family-2 clause-fallthrough instance. With ``spec=None`` the axis
    tuple is chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[ClauseFallthroughSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_clause_fallthrough_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_clause_fallthrough_suite(
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
