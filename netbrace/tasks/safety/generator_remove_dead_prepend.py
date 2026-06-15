"""Family-2 generator — REMOVE-DEAD-PREPEND (the `remove_dead_prepend` mechanism):
a SUBTRACTION-axis, counterintuitive quiet-half trap where DELETING what looks like
dead AS-path cruft flips the best path off the inspection waypoint.

This is a Family-2 (subtraction axis, BUILD_V1.1) sibling of the Family-1 quiet-half
catalog (temporary/frozen_quiet_half_scenario_set.md). It is mechanistically distinct
from every attribute-ADD mechanism in `generator_lp` (lp_raise_alt / lp_drop_way /
prepend_way all ADD or RAISE a value to STEER): here the operator REMOVES a prepend
that looks like leftover cruft, and the removal — by equalizing the AS-path length that
was masking a LATENT, lower-priority discriminator — hands the decision to that latent
attribute and silently moves the egress. The "the safe-looking delete is the dangerous
one" trap (RFC 4271 §9.1.2.2 best-path order; the masked-tiebreak failure mode).

Mechanism (RFC 4271 §9.1.2.2, Breaking Ties (Phase 2), lettered items (a)..(f);
FRR bgp_path_info_cmp): `src` learns the customer /24 over eBGP from BOTH `way` and
`alt`, which share ONE upstream AS (AS_up). On a REAL router that same-first-AS
property is what makes the latent MED eligible for comparison under RFC 4271
§9.1.2.2(c) (MEDs compared only when the leftmost/neighbor AS matches; blog.ipspace.net
BGP-MED-saga + Cisco 13759 — REAL-ROUTER realism only). On the PINNED Batfish digest,
however, gradeability does NOT depend on that gate: Batfish compares MED
UNCONDITIONALLY across ASes (no same-neighbor-AS gate — `BgpRib.java:209` is a bare
`Long.compare`, behaving as if `always-compare-med` were always on; see
knowledge/corpus/batfish/batfish_verified_facts.md "MED comparability ... compares MED
UNCONDITIONALLY"). The outcome is identical either way: both paths share the first AS
anyway, and the strict MED gap (200 > 50) picks the winner whether or not the same-AS
gate is applied.

  * Two attributes are in play, at DIFFERENT priorities:
      - AS_PATH length (item (b), HIGHER priority): in the baseline the ALT path carries
        an AS-path prepend (looks like dead cruft) making it STRICTLY LONGER than the
        WAY path, so `way` wins on AS-path length and src->customer transits the
        inspection node `way`.
      - MED (item (d), LOWER priority, LATENT): `way` advertises a HIGHER MED and `alt`
        a strictly LOWER MED toward `src`. While AS-path decides, MED is never reached
        — the lower-MED preference for `alt` is MASKED.
  * DIFF (bypass): DELETE the prepend on the ALT path. The two AS-path lengths
    EQUALIZE, the item-(b) decision becomes a tie, and the best-path falls through
    ORIGIN (tie, both IGP) to the LATENT item-(d) MED — which strictly favors `alt`.
    `alt` now wins and src->customer silently bypasses `way`.
  * no_op: DELETE a prepend that does NOT equalize the decisive attribute (trim ONE of
    the SEVERAL prepends on the already-losing ALT side). The ALT AS-path stays
    strictly longer than WAY, AS-path length still decides at item (b), MED is never
    reached, `way` still wins. Ground truth is COMPLETELY EMPTY — the calibration trap.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): removing an AS-path prepend never
resets the BGP FSM (RFC 4271 §8: Established exits only on NOTIFICATION/hold-timer/TCP
teardown), so D1=∅. The /24 stays BEST and installed in every RIB (only its chosen
egress moves), so D2=∅; `alt` delivers exactly as `way` did, so D3=∅, D7=∅. The
post-equalization winner is decided by a STRICT MED gap at RFC 4271 §9.1.2.2(d) (NOT
router-id), so there is
exactly one best path each snapshot (maximum-paths default 1) — no equal-cost ECMP tie,
D5=∅, and the oracle is byte-identical. The strict MED gap also means the decision is
made at the MED step BEFORE the nondeterministic router-id/age steps are reached (the
documented Batfish ECMP-multipath trap), which keeps it deterministic AND D5 empty.

Topology (4 nodes, ALL eBGP, directly-connected /30 next-hops, NO statics)::

           AS-path prepend (the KNOB: alt_inbound on src, or dst_outbound on dst)
        +----------------------------------------------------+
        |                                                    |
      src ---/30--- way (AS_up) ---/30(eBGP)--- dst   (the WAY / inspection path)
   (AS_src) |                                      |
            |                                      |   customer /24
            +---/30--- alt (AS_up) ---/30(eBGP)----+   (originated by dst AS_dst,
                                                       dual-homed eBGP to way & alt)

  * src is AS_src; it eBGP-peers DIRECTLY (over the /30 link IP, no multihop, no
    statics) with both way and alt.
  * way AND alt are the SAME upstream AS (AS_up) — this is for REAL-ROUTER realism: on
    a real router the shared first AS is what makes the latent MED eligible under RFC
    4271 §9.1.2.2(c). On the pinned Batfish digest it is NOT a gradeability requirement
    (Batfish compares MED unconditionally — batfish_verified_facts.md), but the shared
    AS keeps the modeled instance faithful to a real bypass. Each eBGP-peers with dst
    (AS_dst) over a directly-connected /30. dst originates the customer /24 on a
    connected dummy host. (way and alt do NOT iBGP-peer each other; src learns one path
    from each directly.)
  * Each upstream sets a MED outbound toward src (`set metric`): way HIGH, alt LOW —
    the latent discriminator. The prepend (the cruft) lives on the ALT path; the change
    deletes it.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {alt_inbound, dst_outbound} — TWO different places the dead prepend lives,
    each a different construct on a different node:
      - alt_inbound : the prepend is on `src`'s INBOUND route-map on the alt eBGP
        session (RM_UPLINK2_IN, `set as-path prepend AS_up AS_up`). change_target=src;
        the reader parses an inbound AS_PATH construct on the receiving router.
      - dst_outbound: the prepend is on `dst`'s OUTBOUND route-map toward the alt
        egress (TO_ALT_OUT, `set as-path prepend AS_dst AS_dst`). change_target=dst;
        the reader parses an outbound AS_PATH construct two hops away from the decider.
    Both make the ALT AS-path strictly longer in the baseline; both delete it.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : DELETE the whole prepend clause -> AS-path equalizes -> the latent MED
        decides -> alt wins. D4+D10 fire; D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : DELETE only ONE of the two prepends -> ALT AS-path still strictly
        longer -> way still wins. COMPLETELY EMPTY ground truth. The prose is
        indistinguishable in style from the bypass edit; only careful best-path
        reasoning separates "remove the whole cruft" from "trim one of the cruft".

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): THREE
distinct ASNs (src / the shared upstream AS_up / dst), loopback block, link /30
supernet, customer /24, and node base name are all drawn deterministically from the
seed. Same seed ⇒ byte-identical instance; different seed ⇒ a novel instance.

Determinism contract (oracle_determinism_spec_v1.md class STATIC-DET): every best-path
decision is STRICT in both snapshots — PRE by an AS-path-length gap (RFC 4271
§9.1.2.2(b)), POST by a MED gap (§9.1.2.2(d)) — so exactly one best path at src each
snapshot, no equal-cost ECMP tie, maximum-paths default 1. Determinism comes from that
STRICT MED gap (200 vs 50): it yields a single best path BEFORE the nondeterministic
router-id/age tie-breaks are ever reached. It does NOT come from any same-AS
"comparison eligibility" gate — Batfish compares MED unconditionally regardless of the
leftmost AS (batfish_verified_facts.md), so eligibility is never in question on the
pinned digest. (`bgp deterministic-med`/`always-compare-med` are NOT modeled by Batfish
and are deliberately NOT emitted; they are unnecessary because Batfish's default
comparator already behaves as if always-compare-med were on.) D4 is scored by
ExtendedOracle._waypoint_diff as the all-traces-transit invariant; D10 by the matching
kind="waypoint" IntentInvariant.

Public API mirrors generator_lp:
    generate_remove_dead_prepend_suite(n, base_seed=...)    -> list[Scenario]
    generate_remove_dead_prepend_all_combos(seed=...)       -> list[Scenario]
    generate_remove_dead_prepend_instance(seed, spec=None)  -> Scenario
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
KNOB_VALUES = ("alt_inbound", "dst_outbound")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# MED values advertised toward src by the two upstream egresses. way HIGH, alt LOW —
# a STRICT gap so the post-equalization decision at the MED step is unambiguous (no
# router-id fall-through -> no Batfish ECMP-multipath D5 artifact). Distinct enough that
# any accidental +/-1 confusion cannot tie them.
_MED_WAY = 200
_MED_ALT = 50


@dataclass(frozen=True)
class RemoveDeadPrependSpec:
    """A point in the Family-2 remove-dead-prepend space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[RemoveDeadPrependSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[RemoveDeadPrependSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(RemoveDeadPrependSpec(knob, effect))
    return out


def enumerable_count() -> int:
    """Number of distinct axis combinations (each ×∞ randomized seeds)."""
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). THREE distinct ASNs: src, the shared upstream
# (way + alt = AS_up), and the customer dst. A distinct sub-band from generator_lp's
# 4_200_1xx so a generated instance never collides with that sibling family.
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

    src_asn: int             # src's own AS (eBGP to both upstreams)
    up_asn: int              # the SHARED upstream AS (way + alt) — the MED crux
    dst_asn: int             # the customer AS (originates the /24)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string
    alt_post: int            # alt prepend count AFTER the edit (the ADDED count; both twins)
    alt_pre: int             # alt prepend count BEFORE the edit (the REMOVED count; both twins)


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    # Three DISTINCT ASNs: src, the shared upstream, dst.
    asns: list[int] = []
    while len(asns) < 3:
        a = rng.randint(_ASN_LO, _ASN_HI)
        if a not in asns:
            asns.append(a)
    src_asn, up_asn, dst_asn = asns

    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    # COUNT-SYMMETRY (prepend-count/delta leak fix): BOTH twins MODIFY the ALT prepend
    # from alt_pre -> alt_post with the SAME per-seed count distribution; only the WAY-side
    # FIXED count W (an UNCHANGED line, set per-effect in the renderer) realizes the routing
    # outcome (W = alt_post -> equalize -> MED -> alt wins, the trap; W = alt_post - 1 -> alt
    # stays strictly longer -> way wins, inert). Drawn LAST so addressing is byte-stable.
    #   alt_post in {2,3} (>=2 so the no_op W = alt_post-1 >= 1); alt_pre = alt_post + offset,
    #   offset in {1,2}, so alt_pre in {3,4,5} and PRE way (W <= alt_post) < alt_pre.
    alt_post = rng.choice((2, 3))
    alt_pre = alt_post + rng.choice((1, 2))

    return _Params(src_asn=src_asn, up_asn=up_asn, dst_asn=dst_asn,
                   loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name=name,
                   alt_post=alt_post, alt_pre=alt_pre)


# --------------------------------------------------------------------------- #
# Topology builder: src dual-homed (eBGP) to way + alt (SAME AS_up), each eBGP to dst.
# Deterministic addressing derived from the randomized blocks.
# Links, fixed order (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    """A concrete, addressed all-eBGP topology for one instance."""

    params: _Params
    spec: RemoveDeadPrependSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: RemoveDeadPrependSpec, params: _Params) -> _Topo:
    name = dict(params.name)

    rid_index = {"src": 1, "way": 2, "alt": 3, "dst": 4}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets, one per link, carved from the link block:
    #   link0 src-way  base .0  (src=.1, way=.2)
    #   link1 src-alt  base .4  (src=.5, alt=.6)
    #   link2 way-dst  base .8  (way=.9, dst=.10)
    #   link3 alt-dst  base .12 (alt=.13, dst=.14)
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
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# leak_ms / generator_lp format). All eBGP, directly-connected /30 peers, NO statics.
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


# --------------------------------------------------------------------------- #
# src: eBGP to way + alt (both AS_up). The alt_inbound knob places the dead prepend on
# src's INBOUND route-map toward alt; src applies no LP (equal preference) so the
# decision falls to AS-path then MED.
# --------------------------------------------------------------------------- #
def _way_fixed_count(topo: _Topo) -> int:
    """The WAY-side FIXED prepend count W (an UNCHANGED line). bypass: W = alt_post (so the
    alt edit equalizes -> AS-path tie -> latent MED decides -> alt wins). no_op: W =
    alt_post - 1 (alt_post > W -> alt stays strictly longer -> way wins -> inert)."""
    return topo.params.alt_post if topo.spec.effect == "bypass" else topo.params.alt_post - 1


def _alt_inbound_prepend_count(topo: _Topo) -> int:
    """Number of prepends on src's alt inbound map for THIS knob/effect baseline."""
    # Baseline always has TWO prepends on the alt path (so a no_op can trim one and
    # still leave a strict gap). For dst_outbound the prepend lives elsewhere, so src
    # has NONE.
    return topo.params.alt_pre if topo.spec.knob == "alt_inbound" else 0


def _src_config(topo: _Topo, *, alt_prepends: Optional[int] = None) -> str:
    """src config. ``alt_prepends`` overrides the alt-inbound prepend count (used to
    render the POST snapshot for the alt_inbound knob); None => the baseline count."""
    p = topo.params
    if alt_prepends is None:
        alt_prepends = _alt_inbound_prepend_count(topo)

    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name["src"], topo.loopback["src"], eth, [])

    body = [ib, _frr_header(topo.name["src"]), fb]

    # WAY session inbound: a FIXED ONE prepend (the equalization target). Only emitted
    # for the alt_inbound knob (where the prepends live on src). This makes way's
    # AS-path length 1, so the bypass equalizes alt to 1 (tie -> MED) and the no_op
    # grows alt to 3 (inert), BOTH as one-line MODIFIES of the alt map -- never as an
    # add/delete asymmetry (the edit-kind-symmetry / line-count leak fix).
    if topo.spec.knob == "alt_inbound":
        way_prep = " ".join(str(p.up_asn) for _ in range(_way_fixed_count(topo)))
        body.append(
            "route-map RM_UPLINK1_IN permit 10\n"
            f" set as-path prepend {way_prep}\n!\n"
        )
    # Inbound map on the alt session. For the alt_inbound knob the dead prepend lives
    # here; the bypass deletes the prepend line, the no_op trims it to one. For the
    # dst_outbound knob src applies no inbound prepend at all (alt_prepends == 0) — but
    # we still emit the (prependless) permit-10 map so the session shape is uniform and
    # the inbound policy is present (idiomatic; not strictly required under `traditional`).
    if alt_prepends > 0:
        prepend = " ".join(str(p.up_asn) for _ in range(alt_prepends))
        body.append(
            "route-map RM_UPLINK2_IN permit 10\n"
            f" set as-path prepend {prepend}\n!\n"
        )
    else:
        body.append("route-map RM_UPLINK2_IN permit 10\n!\n")

    body.append(f"router bgp {p.src_asn}\n")
    body.append(f" bgp router-id {topo.loopback['src']}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.up_asn}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.up_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback['src']}/32\n")
    if topo.spec.knob == "alt_inbound":
        body.append(f"  neighbor {topo.ip[('way', 'src')]} route-map RM_UPLINK1_IN in\n")
    body.append(f"  neighbor {topo.ip[('alt', 'src')]} route-map RM_UPLINK2_IN in\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# way / alt (both AS_up): eBGP to src and to dst. Each sets a MED outbound toward src
# (the latent discriminator). way HIGH MED, alt LOW MED.
# --------------------------------------------------------------------------- #
def _upstream_config(topo: _Topo, role: str, *, dst_alt_prepends: Optional[int] = None) -> str:
    """way or alt. ``dst_alt_prepends`` is unused here (the dst_outbound prepend lives
    on dst); kept symmetric with the dst renderer for clarity."""
    p = topo.params
    med = _MED_WAY if role == "way" else _MED_ALT
    map_name = "MED_TO_SRC_OUT"

    eth = [("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name[role], topo.loopback[role], eth, [])
    body = [ib, _frr_header(topo.name[role]), fb]

    # Outbound MED toward src (the masked latent discriminator).
    body.append(f"route-map {map_name} permit 10\n set metric {med}\n!\n")

    body.append(f"router bgp {p.up_asn}\n")
    body.append(f" bgp router-id {topo.loopback[role]}\n")
    body.append(f" neighbor {topo.ip[('src', role)]} remote-as {p.src_asn}\n")
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.dst_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback[role]}/32\n")
    body.append(f"  neighbor {topo.ip[('src', role)]} route-map {map_name} out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# dst (AS_dst): originates the customer /24, eBGP to way + alt. The dst_outbound knob
# places the dead prepend on dst's OUTBOUND map toward the alt egress.
# --------------------------------------------------------------------------- #
def _dst_outbound_prepend_count(topo: _Topo) -> int:
    return topo.params.alt_pre if topo.spec.knob == "dst_outbound" else 0


def _dst_config(topo: _Topo, *, alt_prepends: Optional[int] = None) -> str:
    """dst config. ``alt_prepends`` overrides the outbound-toward-alt prepend count
    (used to render the POST snapshot for the dst_outbound knob)."""
    p = topo.params
    if alt_prepends is None:
        alt_prepends = _dst_outbound_prepend_count(topo)

    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    ib, fb = _ifaces_intf_text(topo.name["dst"], topo.loopback["dst"], eth, dummies)
    body = [ib, _frr_header(topo.name["dst"]), fb]

    # WAY-facing outbound: a FIXED ONE prepend (the equalization target) for the
    # dst_outbound knob, so the bypass MODIFIES the alt prepend 2 -> 1 (equalize -> MED)
    # and the no_op MODIFIES it 2 -> 3 (inert) -- both one-line modifies (line-count fix).
    if topo.spec.knob == "dst_outbound":
        way_prep = " ".join(str(p.dst_asn) for _ in range(_way_fixed_count(topo)))
        body.append(
            "route-map TO_WAY_OUT permit 10\n"
            f" set as-path prepend {way_prep}\n!\n"
        )
    # Outbound map toward the alt egress. For the dst_outbound knob the dead prepend
    # lives here; bypass deletes it, no_op trims it to one. For the alt_inbound knob dst
    # applies no outbound prepend (alt_prepends == 0) but we still emit the permit-10
    # map so the toward-alt session shape is uniform across knobs.
    if alt_prepends > 0:
        prepend = " ".join(str(p.dst_asn) for _ in range(alt_prepends))
        body.append(
            "route-map TO_ALT_OUT permit 10\n"
            f" set as-path prepend {prepend}\n!\n"
        )
    else:
        body.append("route-map TO_ALT_OUT permit 10\n!\n")

    body.append(f"router bgp {p.dst_asn}\n")
    body.append(f" bgp router-id {topo.loopback['dst']}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.up_asn}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.up_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback['dst']}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    if topo.spec.knob == "dst_outbound":
        body.append(f"  neighbor {topo.ip[('way', 'dst')]} route-map TO_WAY_OUT out\n")
    body.append(f"  neighbor {topo.ip[('alt', 'dst')]} route-map TO_ALT_OUT out\n")
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
# The change: a one-line MODIFY of the alt prepend count. EDIT-KIND-SYMMETRIC (line-count
# leak fix): bypass shortens 2 -> 1 (equalize with the way side's FIXED 1 -> AS-path tie ->
# latent MED decides -> alt wins); no_op lengthens 2 -> 3 (alt still strictly longer -> way
# wins -> inert). BOTH are a single +1/-1 modify; neither adds nor deletes a line, so the
# diff +/- line count carries zero bypass/no_op label info. One node touched.
# --------------------------------------------------------------------------- #
def _apply_change(topo: _Topo) -> tuple[str, str]:
    """Return (change_target_node_name, unified-diff) for this (knob, effect)."""
    knob, effect = topo.spec.knob, topo.spec.effect
    # BOTH twins MODIFY the alt prepend alt_pre -> alt_post (IDENTICAL count distribution);
    # only the WAY-side fixed count W (cross-config, in _way_fixed_count) differs, realizing
    # the outcome: bypass equalizes (W == alt_post), no_op leaves alt strictly longer.
    new_count = topo.params.alt_post

    if knob == "alt_inbound":
        node = topo.name["src"]
        before = _src_config(topo)                       # 2 prepends on alt
        after = _src_config(topo, alt_prepends=new_count)
    else:  # dst_outbound
        node = topo.name["dst"]
        before = _dst_config(topo)                       # 2 prepends on alt
        after = _dst_config(topo, alt_prepends=new_count)

    if before == after:
        raise RuntimeError(
            f"change for {topo.spec.dims_label()} produced no diff on {node} "
            f"(seed render drift)"
        )
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
# phrased the SAME way: the prose names only WHICH route-map's `set as-path prepend`
# clause is removed/shortened, never whether the best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    # BOTH twins SHORTEN the alt `set as-path prepend` clause (alt_pre -> alt_post); the
    # sentence shape and verb are IDENTICAL across bypass/no_op, so neither the prose nor a
    # diff count feature distinguishes them -- only reading the WAY-side fixed prepend count
    # (cross-config) reveals whether the shortened alt count now EQUALS the way count
    # (equalize -> the latent MED decides) or stays above it (inert). Routing reasoning only.
    verb = "shorten the `set as-path prepend` clause by one or more entries"
    if knob == "alt_inbound":
        node = topo.name["src"]
        return (
            f"On `{node}` (AS{topo.params.src_asn}), edit the inbound eBGP route-map "
            f"`RM_UPLINK2_IN` to {verb} (an AS_PATH adjustment that drops a leftover "
            f"prepend). See the diff."
        )
    # dst_outbound
    node = topo.name["dst"]
    return (
        f"On `{node}` (AS{topo.params.dst_asn}), edit the outbound eBGP route-map "
        f"`TO_ALT_OUT` to {verb} (an AS_PATH adjustment that drops a leftover "
        f"prepend). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to clean up a leftover AS_PATH prepend "
    "on this path."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: RemoveDeadPrependSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    change_target, patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + all loopbacks (negative controls).
    watched = [f"{topo.loopback[r]}/32" for r in _ROLES] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host.
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint as a kind="waypoint" IntentInvariant so
    # the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"remove-dead-prepend quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_remove_dead_prepend_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    return Scenario(
        name=name,
        nodes=[src, way, alt, dst],
        pre_configs=pre,
        change_target=change_target,
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
def generate_remove_dead_prepend_instance(
    seed: int, spec: Optional[RemoveDeadPrependSpec] = None
) -> Scenario:
    """Emit ONE Family-2 remove-dead-prepend instance. With ``spec=None`` the axis
    tuple is chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[RemoveDeadPrependSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_remove_dead_prepend_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_remove_dead_prepend_suite(
    n: int, *, base_seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct
    seed per position; wrap with a fresh seed offset when ``n`` exceeds the combo count,
    giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
