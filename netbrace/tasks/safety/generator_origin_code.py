r"""Family-2 generator — ORIGIN-CODE TIEBREAK FLIP (the `origin_code` mechanism): a
DUAL-ORIGIN customer prefix whose two copies reach `src` tied on LOCAL_PREF and
AS_PATH length, so the BGP best-path decision falls to the ORIGIN step (RFC 4271 §9.1.1
step 5: IGP < EGP < INCOMPLETE). The decisive change swaps ONE side's origination
method between `network` (ORIGIN=igp) and `redistribute static` (ORIGIN=incomplete),
flipping the ORIGIN ordering so the tie now goes to a LATENT STRICT MED that favors the
bypass egress. No LOCAL_PREF, no AS_PATH, no prefix and no session is touched.

This is the hardest comparator in the quiet-half catalog (Family 2, BUILD_V1.1): unlike
the Family-1 underlay-displacement mechanisms (IGP cost / redistribute-AD / next-hop
elimination) the diff lives entirely in the BGP origination namespace, yet it is NOT a
first-order LOCAL_PREF/AS_PATH edit a model catches by reflex — it is a `network` ↔
`redistribute` swap whose only routing consequence is an ORIGIN-code change two
best-path steps deep. The reader must know the RFC 4271 best-path order AND that
`network` stamps ORIGIN=igp while `redistribute static` stamps ORIGIN=incomplete.

Mechanism (RFC 4271 §9.1.1 best-path order — LOCAL_PREF (step 2) > AS_PATH length
(step 4) > ORIGIN (step 5) > MED (step 6, same-neighbor-AS only)): `src` learns the
customer /24 over TWO eBGP paths that are byte-identical on LOCAL_PREF (default 100) and
AS_PATH length (both [AS_egr], length 1, because `way` and `alt` ORIGINATE the prefix —
they do not re-advertise a dst-originated copy), so no BGP attribute above ORIGIN can
decide. The two paths differ ONLY in ORIGIN code and in a latent MED:

  * PRE: the way-side copy is originated by `network` (ORIGIN=igp) and the alt-side by
    `redistribute static` (ORIGIN=incomplete). igp < incomplete, so the way copy wins at
    the ORIGIN step and src->customer transits the inspection node `way`. The latent MED
    (way=200, alt=50) is NEVER consulted PRE because ORIGIN already decided.
  * DIFF (bypass): swap the deciding side's origination method (`network`↔`redistribute
    static`) so BOTH copies become ORIGIN=incomplete. The ORIGIN step now TIES, and the
    decision falls through to the MED step (RFC 4271 step 6). Because `way` and `alt`
    advertise to `src` from the SAME neighboring AS (AS_egr), Batfish compares their MED
    unconditionally (the always-/deterministic-med config is not even needed, and is
    deliberately not emitted — it is unparseable on the pinned digest), and alt's 50 < 200
    wins → src->customer silently bypasses `way`.
  * POST/no_op: a `network`↔`redistribute` swap of the SAME KIND applied to an
    IRRELEVANT prefix (the edited egress's OWN loopback /32), so the customer /24's
    ORIGIN ordering is untouched, the way copy keeps its igp edge, and the best path
    stays on `way`. Ground truth is COMPLETELY EMPTY.

Why MED, not router-id, is the final discriminator (the falsified-tiebreak gate,
docs/oracle_determinism_spec_v1.md / verified live on the pinned digest): once ORIGIN
ties, the next BGP steps are MED (step 6), eBGP-over-iBGP (step 7, both eBGP → tie), and
IGP-metric (step 8, directly-connected eBGP → tie); if nothing breaks the tie before
router-id (step 9) Batfish installs an ECMP MULTIPATH, which fires D5 and KILLS D4. The
SAME-neighbor-AS MED gap (way 200 vs alt 50) is the STRICT discriminator that resolves
the decision BEFORE router-id is ever reached, in BOTH snapshots — exactly one best path
at `src` each time, no ECMP tie, maximum-paths default 1. `bgp deterministic-med` /
`bgp always-compare-med` are NOT modeled by the pinned Batfish digest (deterministic-med
is unparseable) and are NOT emitted; the same-neighbor-AS comparison is unconditional, so
it is exploited directly.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): a `network`/`redistribute` edit is
not a session parameter and never resets a BGP FSM (RFC 4271 §8: Established exits only
on NOTIFICATION/hold-timer/TCP teardown), so D1=∅. The /24 stays present-and-best in
every RIB across the diff (only WHICH copy wins at src changes; both copies remain
valid), so D2=∅; `alt` delivers the /24 exactly as `way` did (a real, verified path), so
D3=∅, D7=∅. The strict MED gap means exactly one best path in each snapshot — D5=∅ and
the oracle is byte-identical. A naive model predicts a session reset or a prefix loss; the
oracle says ONLY the waypoint (D4) and the matching intent (D10) move.

Topology (5 nodes, ALL eBGP, directly-connected /30 next-hops — no statics except the
two that the DUAL-ORIGIN itself requires, see below)::

           way (AS_egr) --/30-- dst (AS_egr) --/30-- host (AS_egr; customer /24)
          /  way ORIGINATES the customer /24                       ^
   src --/30                                                       | the /24 lives here
  (AS_src) \  alt ORIGINATES the customer /24                      |
           alt (AS_egr) --/30-- dst -----------------------------/

  * `src` (AS_src) eBGP-peers DIRECTLY (over the /30 link IP, no update-source, no
    multihop) with both `way` (AS_egr) and `alt` (AS_egr). Both upstreams are the SAME
    AS so the two customer paths `src` receives share neighbor-AS = AS_egr, which is what
    makes the latent MED comparable (RFC 4271 step 6 compares MED only across
    same-neighbor-AS paths).
  * `way`, `alt`, `dst`, `host` all live in AS_egr (one customer/egress AS). `way` and
    `alt` each ORIGINATE the customer /24 toward `src` — way via `network`, alt via
    `redistribute static` — so `src`'s two received paths have AS_PATH=[AS_egr], length 1
    (the AS_PATH-length tie that forces the decision down to ORIGIN). They do NOT learn
    the /24 from `dst` over BGP (that would lengthen the AS_PATH and break the tie).
  * The customer /24 physically lives on `host`'s connected dummy interface; `dst`
    forwards to `host` and `way`/`alt` forward to `dst`, all via the two REQUIRED static
    routes toward the /24 (the dual-origin construction needs them: `redistribute static`
    has nothing to redistribute without a static, and `network <cust>` only originates a
    prefix that is present in the RIB — the static makes it present and forwardable).
    These statics are GENUINELY REQUIRED by the mechanism, not a recursive-next-hop
    crutch: they exist to make the two ORIGINATIONS legal and the prefix deliverable, and
    they are inside AS_egr's forwarding plane, never on `src`.

Structural axes (each a genuinely distinct config-reading task or a calibration control
— NOT a clone):

  * knob ∈ {way_to_incomplete, alt_to_igp} — two DIFFERENT origination-method edits that
    both collapse the ORIGIN ordering to a tie, each on the OPPOSITE device and the
    OPPOSITE direction of swap (so a model cannot pattern-match one rewrite):
      - way_to_incomplete : PRE way=`network` (igp), alt=`redistribute static`
        (incomplete); way wins on ORIGIN. The change swaps WAY's customer origination
        from `network` to `redistribute static`, so way's ORIGIN flips igp→incomplete,
        the ORIGIN step ties, and the latent MED (alt 50 < way 200) takes over.
      - alt_to_igp : SAME PRE (way igp wins). The change swaps ALT's customer
        origination from `redistribute static` to `network`, so alt's ORIGIN flips
        incomplete→igp, the ORIGIN step ties, and the SAME latent MED takes over. Same
        outcome class, opposite device + opposite rewrite, a distinct construct to read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the swap actually collapses the customer /24's ORIGIN ordering. D4+D10
        fire; D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of `network`↔`redistribute` swap applied to the edited
        egress's OWN loopback /32 (an irrelevant prefix), leaving the customer /24's
        ORIGIN ordering — and therefore the best path — untouched. Ground truth is
        COMPLETELY EMPTY across ALL dimensions. The prose is indistinguishable in style
        from a bypass edit; only careful best-path reasoning (which prefix's ORIGIN
        actually moved) separates them.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): the egress
AS, the source AS, the loopback block, the link /30 supernet, the customer /24, and the
node base name are all drawn deterministically from the seed. Same seed ⇒ byte-identical
instance; different seed ⇒ a novel instance even for this public mechanism.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path decision
is STRICT in both snapshots — PRE the ORIGIN gap (igp < incomplete) decides; POST/bypass
the MED gap (50 < 200) decides at a step ABOVE router-id; POST/no_op nothing about the
customer decision moves. Exactly one best path at `src` each time, no equal-cost ECMP
tie, maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as the
all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.

LIVE-VERIFIED (pinned batfish/allinone:nethelm @ 09817554db90, light pass on network
"netbrace_b23_origin_code"): PRE src best = igp via way (ORIGIN beats incomplete; MED
200 ignored), trace src->way->dst->host; bypass swaps the deciding origination, both
copies become incomplete, the same-neighbor-AS MED (alt 50 < way 200) wins, trace
src->alt->dst->host; reachability preserved both ways; bypass combos -> {waypoint,
intent} ONLY, no_op combos -> COMPLETELY EMPTY, bypass combos 3x byte-identical (the lead
re-runs the authoritative 10x).

Public API mirrors generator_lp / generator_igp_metric:
    generate_origin_code_suite(n, base_seed=...)        -> list[Scenario]
    generate_origin_code_all_combos(seed=...)           -> list[Scenario]
    generate_origin_code_instance(seed, spec=None)      -> Scenario
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
KNOB_VALUES = ("way_to_incomplete", "alt_to_igp")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# The latent MED carried toward src on each upstream's customer-/24 advertisement.
# way's is STRICTLY HIGHER than alt's so that once the ORIGIN step ties (post bypass)
# the same-neighbor-AS MED comparison favors alt (the bypass egress). The gap is the
# strict discriminator that keeps the decision off router-id (no D5 ECMP).
_MED_WAY = 200
_MED_ALT = 50


@dataclass(frozen=True)
class OriginCodeSpec:
    """A point in the Family-2 origin-code generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[OriginCodeSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[OriginCodeSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(OriginCodeSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the source AS (src) and the
# egress AS (way/alt/dst/host all share it -> the two customer paths src receives have
# the SAME neighbor-AS, which is what makes the latent MED comparable). Clear of the
# hand-authored 65000 family.
_ASN_LO, _ASN_HI = 4_200_300_000, 4_200_399_999

_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]

_ROLES = ("src", "way", "alt", "dst", "host")


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    src_asn: int             # the source AS (eBGP to both upstreams)
    egr_asn: int             # way/alt/dst/host share this (so MED is comparable at src)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    src_asn = rng.randint(_ASN_LO, _ASN_HI)
    egr_asn = src_asn
    while egr_asn == src_asn:
        egr_asn = rng.randint(_ASN_LO, _ASN_HI)

    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    return _Params(src_asn=src_asn, egr_asn=egr_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net, name=name)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst,
# dst-host. Deterministic addressing derived from the randomized blocks.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: OriginCodeSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: OriginCodeSpec, params: _Params) -> _Topo:
    name = dict(params.name)

    rid_index = {"src": 1, "way": 2, "alt": 3, "dst": 4, "host": 5}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets, one per link, carved from the link block:
    #   src-way  base .0  (src=.1,  way=.2)
    #   src-alt  base .4  (src=.5,  alt=.6)
    #   way-dst  base .8  (way=.9,  dst=.10)
    #   alt-dst  base .12 (alt=.13, dst=.14)
    #   dst-host base .16 (dst=.17, host=.18)
    ip: dict[tuple[str, str], str] = {
        ("src", "way"): addr(1), ("way", "src"): addr(2),
        ("src", "alt"): addr(5), ("alt", "src"): addr(6),
        ("way", "dst"): addr(9), ("dst", "way"): addr(10),
        ("alt", "dst"): addr(13), ("dst", "alt"): addr(14),
        ("dst", "host"): addr(17), ("host", "dst"): addr(18),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback,
                 rid_index=rid_index, ip=ip, customer_prefix=customer_prefix,
                 customer_ip=customer_ip)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 / generator_lp format). All eBGP, directly-connected /30 peers.
# --------------------------------------------------------------------------- #
_FRR_VER = "frr version 10.6.1"
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
        f"{_FRR_VER}\n"
        "frr defaults traditional\n"
        f"hostname {node_name}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


# --------------------------------------------------------------------------- #
# src: AS_src, eBGP to way + alt (directly-connected /30s), NO policy. The two
# received customer paths are tied on LOCAL_PREF + AS_PATH-length, so ORIGIN decides.
# --------------------------------------------------------------------------- #
def _src_config(topo: _Topo) -> str:
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}"))
    body.append(f"router bgp {p.src_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.egr_asn}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.egr_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# way / alt: AS_egr egresses that ORIGINATE the customer /24 toward src. The
# origination METHOD (network=igp vs redistribute static=incomplete) is the KNOB;
# the latent MED is carried toward src. Both static-route the /24 to dst (REQUIRED by
# the dual-origin construction — see module docstring). The loopback is originated by
# `network <lo>/32` by default; the no_op edit swaps THAT to `redistribute connected`.
# --------------------------------------------------------------------------- #
def _egress_config(topo: _Topo, role: str, *, origin: str, med: int,
                   loop_via_redist: bool) -> str:
    """Render way/alt.

    ``origin`` ∈ {"network", "redistribute"} controls how the CUSTOMER /24 is
    originated (igp vs incomplete). ``med`` is the MED set toward src on the customer
    advertisement. ``loop_via_redist`` (the no_op state) originates the OWN loopback /32
    via `redistribute connected` instead of `network <lo>/32` (an irrelevant-prefix
    swap that does not touch the customer /24's ORIGIN ordering).
    """
    p = topo.params
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}"))
    # REQUIRED static toward the customer /24 (via dst): makes the prefix present in
    # the RIB (so `network` can originate it) AND redistributable (so `redistribute
    # static` has something to inject) AND forwardable to dst->host.
    body.append(f"ip route {topo.customer_prefix} {topo.ip[('dst', role)]}\n")

    if origin == "network":
        # ORIGIN=igp. MED set via an outbound route-map toward src (named per role so
        # the two devices read distinctly).
        rm = f"SET_MED_{role.upper()}"
        body.append(f"route-map {rm} permit 10\n set metric {med}\n!\n")
    else:  # redistribute static -> ORIGIN=incomplete
        # The redistribution route-map matches the customer /24 and stamps the MED.
        body.append(
            f"ip prefix-list CUST_PL seq 5 permit {topo.customer_prefix}\n!\n")
        body.append(
            f"route-map REDIST_CUST permit 10\n"
            f" match ip address prefix-list CUST_PL\n"
            f" set metric {med}\n!\n")

    if loop_via_redist:
        # no_op state: originate the OWN loopback /32 via redistribute connected.
        body.append(f"ip prefix-list LOOP_PL seq 5 permit {lo}/32\n!\n")
        body.append(
            f"route-map REDIST_LOOP permit 10\n"
            f" match ip address prefix-list LOOP_PL\n!\n")

    body.append(f"router bgp {p.egr_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('src', role)]} remote-as {p.src_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    if loop_via_redist:
        body.append("  redistribute connected route-map REDIST_LOOP\n")
    else:
        body.append(f"  network {lo}/32\n")
    if origin == "network":
        body.append(f"  network {topo.customer_prefix}\n")
        body.append(
            f"  neighbor {topo.ip[('src', role)]} route-map SET_MED_{role.upper()} out\n")
    else:
        body.append("  redistribute static route-map REDIST_CUST\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# dst: AS_egr transit between the two egresses and host. NO BGP (forwarding-only);
# static toward the customer /24 via host. host: AS_egr, holds the customer /24 on a
# connected dummy interface (the real destination the traceroute is accepted at).
# --------------------------------------------------------------------------- #
def _dst_config(topo: _Topo) -> str:
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}"),
           ("eth3", f"{topo.ip[('dst', 'host')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["dst"], lo, eth, []), _frr_header(topo.name["dst"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth3", f"{topo.ip[('dst', 'host')]}{_LINK_MASK}"))
    body.append(f"ip route {topo.customer_prefix} {topo.ip[('host', 'dst')]}\n")
    return "".join(body)


def _host_config(topo: _Topo) -> str:
    lo = topo.loopback["host"]
    eth = [("eth1", f"{topo.ip[('host', 'dst')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["host"], lo, eth, dummies), _frr_header(topo.name["host"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('host', 'dst')]}{_LINK_MASK}"))
    body.append(_plain_iface("dum0", f"{topo.customer_ip}/24"))
    return "".join(body)


# --------------------------------------------------------------------------- #
# The PRE baseline. way originates via `network` (ORIGIN=igp, MED 200); alt via
# `redistribute static` (ORIGIN=incomplete, MED 50). way wins at the ORIGIN step.
# --------------------------------------------------------------------------- #
def _baseline_configs(topo: _Topo) -> dict[str, str]:
    way = _egress_config(topo, "way", origin="network", med=_MED_WAY,
                         loop_via_redist=False)
    alt = _egress_config(topo, "alt", origin="redistribute", med=_MED_ALT,
                         loop_via_redist=False)
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: way,
        topo.name["alt"]: alt,
        topo.name["dst"]: _dst_config(topo),
        topo.name["host"]: _host_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change. A `network`↔`redistribute` origination-method swap on ONE egress.
# The change target is `way` for knob=way_to_incomplete, `alt` for knob=alt_to_igp.
# bypass swaps the CUSTOMER /24 origination (flips the decisive ORIGIN); no_op swaps
# the OWN-LOOPBACK origination (leaves the customer ORIGIN ordering intact).
# --------------------------------------------------------------------------- #
def _change_target(spec: OriginCodeSpec) -> str:
    return "way" if spec.knob == "way_to_incomplete" else "alt"


def _egress_config_for(topo: _Topo, role: str, *, customer_as_redistribute: bool,
                       loop_via_redist: bool) -> str:
    """Render a given egress in an arbitrary origination state.

    ``customer_as_redistribute`` True => customer /24 via `redistribute static`
    (incomplete); False => via `network` (igp). The MED is the role's fixed MED so the
    advertisement carries the same MED regardless of origination method.
    """
    med = _MED_WAY if role == "way" else _MED_ALT
    origin = "redistribute" if customer_as_redistribute else "network"
    return _egress_config(topo, role, origin=origin, med=med,
                          loop_via_redist=loop_via_redist)


def _apply_change(topo: _Topo) -> str:
    spec = topo.spec
    role = _change_target(spec)

    # PRE state of the edited egress:
    #   way (knob1): customer via `network` (igp);  alt (knob2): customer via
    #   `redistribute static` (incomplete). Loopback via `network <lo>/32` in both.
    way_is_network_pre = True   # way originates customer via network PRE
    alt_is_network_pre = False  # alt originates customer via redistribute PRE
    pre_customer_redist = (not way_is_network_pre) if role == "way" else (not alt_is_network_pre)
    before = _egress_config_for(topo, role,
                                customer_as_redistribute=pre_customer_redist,
                                loop_via_redist=False)

    if spec.effect == "bypass":
        # Swap the CUSTOMER /24 origination method -> flip its ORIGIN code.
        after = _egress_config_for(topo, role,
                                   customer_as_redistribute=(not pre_customer_redist),
                                   loop_via_redist=False)
    else:
        # no_op: swap the OWN-LOOPBACK origination method (network -> redistribute
        # connected). The customer /24 origination is unchanged -> ORIGIN ordering and
        # the best path are untouched.
        after = _egress_config_for(topo, role,
                                   customer_as_redistribute=pre_customer_redist,
                                   loop_via_redist=True)

    if before == after:
        raise RuntimeError(
            f"change for {spec.dims_label()} produced no diff (render drift)")
    return _unified(before, after, topo.name[role])


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
# phrased the SAME way: the prose names only WHICH egress's origination method is
# swapped between `network` and `redistribute`, never whether the best path moves or
# which ORIGIN code results. The forbidden-outcome lint (test_generator_family1) bars
# bypass/reroute/no-longer/wins/loses/best-path/etc; config-construct words
# (network, redistribute, prefix-list, metric) ARE allowed — they name what is edited.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    spec = topo.spec
    role = _change_target(spec)
    rname = topo.name[role]
    asn = topo.params.egr_asn
    if spec.effect == "bypass":
        # The customer prefix's origination method is swapped (network<->redistribute).
        if spec.knob == "way_to_incomplete":
            edit = ("swap the customer prefix's origination on this router from a "
                    "`network` statement to a `redistribute static` statement (with a "
                    "matching prefix-list + route-map)")
        else:  # alt_to_igp
            edit = ("swap the customer prefix's origination on this router from a "
                    "`redistribute static` statement (matched by a prefix-list + "
                    "route-map) to a `network` statement")
        return (
            f"On `{rname}` (AS{asn}), {edit} (a one-construct origination-method "
            f"change). See the diff."
        )
    # no_op: swap the OWN-loopback /32 origination method (same construct kind).
    return (
        f"On `{rname}` (AS{asn}), swap the router's own loopback /32 origination from "
        f"a `network` statement to a `redistribute connected` statement (matched by a "
        f"prefix-list + route-map) — a one-construct origination-method change. See "
        f"the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tune how this prefix is originated "
    "into BGP."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: OriginCodeSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    role = _change_target(spec)
    patch = _apply_change(topo)

    src, way, alt, dst, host = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the four egress-side loopbacks + src loopback
    # (negative controls — a model that false-positives on a survivor loses precision).
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "way", "alt", "dst")] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host so the
    # trace terminates at a real connected accept.
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"origin-code quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_origin_code_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    return Scenario(
        name=name,
        nodes=[src, way, alt, dst, host],
        pre_configs=pre,
        change_target=topo.name[role],
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
# Public API (mirrors generator_lp / generator_igp_metric).
# --------------------------------------------------------------------------- #
def generate_origin_code_instance(
    seed: int, spec: Optional[OriginCodeSpec] = None
) -> Scenario:
    """Emit ONE Family-2 origin-code instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[OriginCodeSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_origin_code_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_origin_code_suite(
    n: int, *, base_seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct seed
    per position; wrap with a fresh seed offset when ``n`` exceeds the combo count,
    giving the same structure a NEW randomized instance)."""
    specs = _selected_specs(include_noop)
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, base_seed + i))
    return out
