"""Family-2 generator — FAR-AS AS_PATH PREPEND (the `far_as_prepend` mechanism): the
DECISIVE best-path edit lives in a DIFFERENT AS (the foreign customer `dst`), not on
`src`, yet it silently steers `src`'s best path off the inspection waypoint.

This is the cross-domain-locus sibling of `generator_lp`'s `prepend_way` knob. Both
ride the IDIOMATIC all-eBGP topology (directly-connected /30 eBGP peers, NO OSPF, NO
recursion, NO static crutch) and both flip `src`'s best path via an AS_PATH-length
change at RFC 4271 §9.1.2.2 step 4. The DISTINCTNESS — and the reason this is a
separate mechanism, not a `generator_lp` clone — is the LOCUS of the cause:

  * generator_lp/prepend_way edits an INBOUND route-map on `src` itself (src
    re-weights what it accepts). The operator reading the diff sees the change on the
    very router whose path moves.
  * far_as_prepend edits an OUTBOUND route-map on the FOREIGN customer `dst` (a
    DIFFERENT AS). dst lengthens the AS_PATH it exports toward one upstream; src never
    touches its own config. This is the classic "a downstream/customer prepend
    reshaped our egress and we didn't change anything" surprise — the cause is one AS
    away and the affected router's config is byte-identical pre and post. A model that
    only inspects `change_target`'s neighbors will reason about the wrong device.

Mechanism (RFC 4271 §9.1.2.2 step 4 — "prefer the route with the shortest AS_PATH";
FRR bgp_path_info_cmp aspath-length step): LOCAL_PREF is EQUAL on `src`'s two upstream
sessions, so no LOCAL_PREF can decide and best-path falls through to AS_PATH length.
`dst` originates the customer /24 and applies a PER-NEIGHBOR OUTBOUND `set as-path
prepend <dst-asn>` toward each upstream to tune which upstream carries the shorter
path into `src`:

  * PRE: dst prepends its own ASN once on its session toward `alt` (the bypass
    egress), so the path `src` learns via `alt` is one AS_PATH hop LONGER than via
    `way`. way (shorter AS_PATH) wins and src->customer transits the inspection node
    `way`.
  * DIFF (bypass): dst ADDS a longer outbound prepend toward `way`, making the path
    via `way` STRICTLY longer than the (still-prepended-once) path via `alt`. alt
    (now shorter) wins and src->customer silently bypasses `way`. The change is
    entirely inside dst's AS; `src`'s config does not change.
  * no_op: dst extends the already-longer prepend toward `alt` (the path that was
    already losing). way stays strictly shorter, the winner does not move, and the
    ground truth is COMPLETELY EMPTY.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): an AS_PATH-attribute change on a
received UPDATE never resets the BGP FSM (RFC 4271 §8: Established exits only on
NOTIFICATION/hold-timer/TCP teardown), so D1=∅. The /24 stays BEST and installed in
every RIB (only its winning AS_PATH/egress moves), so D2=∅; `alt` delivers exactly as
`way` did, so D3=∅, D7=∅. A STRICT (non-equal) AS_PATH-length gap in BOTH snapshots
means exactly one best path at `src` each time (maximum-paths default 1, no equal-cost
ECMP tie), so D5=∅ and the oracle is byte-identical. Critically, the strict gap means
the decision is made at the AS_PATH-length step BEFORE the nondeterministic
router-id/age steps are reached (the documented Batfish ECMP-multipath trap), which is
what keeps the result deterministic AND D5 empty.

Topology (4 nodes; ALL eBGP, distinct ASNs, directly-connected /30 next-hops — no
OSPF, no recursion, no statics)::

           OUTBOUND as-path prepend (the KNOB) on dst toward each upstream
        +----------------------------------------------------+
        |                                                    |
      src ---/30--- way (AS_way) ---/30(eBGP)--- dst   (the WAY / inspection path)
   (AS_src) |                                      |
            |                                      |   customer /24
            +---/30--- alt (AS_alt) ---/30(eBGP)---+   (originated by dst,
                                                       dual-homed to way & alt)

  * src is AS_src; it eBGP-peers DIRECTLY (over the /30 link IP, no update-source, no
    multihop) with both way (AS_way) and alt (AS_alt). src applies NO BGP policy —
    its two received customer paths differ ONLY in AS_PATH length.
  * way and alt are distinct upstream ASes; each eBGP-peers with dst (AS_dst) over a
    directly-connected /30 and re-advertises dst's customer /24 to src. The eBGP
    next-hop on each received route is the directly-connected upstream /30 IP, so it
    resolves with NO static route.
  * dst originates the customer /24 on a connected dummy host and applies PER-NEIGHBOR
    OUTBOUND route-maps (RM_TO_WAY_OUT / RM_TO_ALT_OUT). The baseline prepends toward
    alt so way is shorter; the change prepends toward way to flip it. The prepend uses
    dst's OWN ASN (the idiomatic inbound-TE technique) in literal-ASN syntax (`set
    as-path prepend <asn>`), which the pinned Batfish FRR model parses (the `last-as`
    shorthand is NOT modeled — verified live).

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * pre_depth ∈ {1, 2} — how many times dst already prepends toward `alt` in the
    baseline. Both keep way shorter PRE; they change the AS_PATH-length arithmetic the
    reader must do (way=1 vs alt=2, or way=1 vs alt=3) and the magnitude of the
    flipping prepend the bypass edit must add. Same D4 GT class, different numbers to
    parse — a genuine difficulty/numbering variant, not a clone.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : dst adds an outbound prepend toward `way` long enough to make the via-
        way AS_PATH STRICTLY longer than via-alt. D4+D10 fire; D1/D2/D3/D5/D7 = ∅. The
        trap (the cause is in a foreign AS).
      - no_op  : dst EXTENDS the already-longer outbound prepend toward `alt` (the
        already-losing path). way stays strictly shorter, the winner does not move, and
        the ground truth is COMPLETELY EMPTY across ALL dimensions — the calibration
        trap. The prose is indistinguishable in style from a bypass edit; only careful
        best-path reasoning separates them.

That is 2 pre_depths × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): four
DISTINCT ASNs (src/way/alt/dst), the loopback block, the link /30 supernet, the
customer /24, and the node base name are all drawn deterministically from the seed.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path
decision is STRICT at the AS_PATH-length step in both snapshots (a real, non-equal
AS_PATH-length gap) — exactly one best path at `src` in each snapshot, no equal-cost
ECMP tie, maximum-paths default 1. D4 is scored by ExtendedOracle._waypoint_diff as
the all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant.
NO static routes ⇒ no recursive-next-hop artifact.

Public API mirrors generator_lp / generator_igp_metric:
    generate_far_as_prepend_suite(n, base_seed=...)      -> list[Scenario]
    generate_far_as_prepend_all_combos(seed=...)         -> list[Scenario]
    generate_far_as_prepend_instance(seed, spec=None)    -> Scenario
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
PRE_DEPTH_VALUES = (1, 2)
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "pre_depth": PRE_DEPTH_VALUES,
    "effect": EFFECT_VALUES,
}


@dataclass(frozen=True)
class FarAsPrependSpec:
    """A point in the Family-2 far_as_prepend generator space (axis tuple, pre-random)."""

    pre_depth: int   # how many dst-ASN prepends toward alt in the baseline (1 or 2)
    effect: str

    def dims_label(self) -> str:
        return f"d{self.pre_depth}-{self.effect}"


def enumerate_specs() -> list[FarAsPrependSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[FarAsPrependSpec] = []
    for pre_depth in PRE_DEPTH_VALUES:
        for effect in EFFECT_VALUES:
            out.append(FarAsPrependSpec(pre_depth, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). FOUR DISTINCT ASNs (src/way/alt/dst). We draw
# from a band offset from generator_lp's so a far_as_prepend instance never collides
# with an lp instance of the same seed.
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
    swap: bool               # per-seed: exchange the way<->alt PHYSICAL slot (leak fix)


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

    # Per-seed ROLE->POSITION swap (positional-leak fix), drawn LAST so addressing is
    # byte-stable; decides which PHYSICAL slot the waypoint `way` vs bypass `alt` holds.
    swap = _rp.draw_swap(rng)

    return _Params(asn=asn, loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name=name, swap=swap)


# --------------------------------------------------------------------------- #
# Topology builder: src dual-homed (eBGP) to way + alt, each eBGP to dst.
# Links, fixed order (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: FarAsPrependSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: FarAsPrependSpec, params: _Params) -> _Topo:
    rid_index = _rp.swapped_rid_index(
        {"src": 1, "way": 2, "alt": 3, "dst": 4}, params.swap, ("way", "alt"))
    name = _rp.swapped_names(dict(params.name), params.swap, ("way", "alt"))
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved by the (swapped) physical slot so the waypoint side's
    # loopback octet, name suffix and link IPs move per seed.
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

    return _Topo(params=params, spec=spec, name=name, loopback=loopback,
                 rid_index=rid_index, ip=ip, customer_prefix=customer_prefix,
                 customer_ip=customer_ip)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# leak_ms / generator_lp format). All eBGP, directly-connected /30 peers, NO statics.
# --------------------------------------------------------------------------- #
_LINK_MASK = "/30"
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


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


# --------------------------------------------------------------------------- #
# src: NO BGP policy. eBGP to way + alt. The two received customer paths differ
# only in AS_PATH length (LOCAL_PREF equal by default). src's config is BYTE-
# IDENTICAL pre and post — the cause is one AS away (on dst).
# --------------------------------------------------------------------------- #
def _src_config(topo: _Topo) -> str:
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}"))
    body.append(f"router bgp {p.asn['src']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _upstream_config(topo: _Topo, role: str) -> str:
    """way or alt: eBGP to src and to dst, NO policy, NO statics. Re-advertises dst's
    customer /24 to src (prepending its own AS on export, as eBGP does)."""
    p = topo.params
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}"))
    body.append(f"router bgp {p.asn[role]}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('src', role)]} remote-as {p.asn['src']}\n")
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.asn['dst']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# ---- dst's per-neighbor OUTBOUND prepend route-maps (the KNOB lives here) ----- #
# RM_TO_WAY_OUT (toward way) and RM_TO_ALT_OUT (toward alt). The baseline prepends
# dst's OWN ASN `pre_depth` times toward alt so the via-alt AS_PATH is longer and way
# wins; the via-way map carries no prepend in the baseline (a plain permit). The
# change edits ONE of these maps.
def _prepend_line(asn: int, times: int) -> str:
    """`set as-path prepend <asn> <asn> ...` (literal-ASN syntax, Batfish-parseable)."""
    return " set as-path prepend " + " ".join([str(asn)] * times)


def _dst_config(topo: _Topo) -> str:
    p = topo.params
    lo = topo.loopback["dst"]
    dst_asn = p.asn["dst"]
    pre = topo.spec.pre_depth
    # dst's two upstream-facing interfaces are ordered by the PHYSICAL slot of the
    # upstream role (slot-2 role -> eth1, slot-3 role -> eth2); each outbound prepend
    # route-map is named after the UPSTREAM NODE NAME (swapped per seed). The baseline
    # prepend toward `alt` keeps the via-alt path longer (so way wins PRE). Neither the
    # eth index nor the route-map name reveals which side is the waypoint.
    lo_role = "way" if topo.loopback["way"].endswith(".2") else "alt"
    hi_role = "alt" if lo_role == "way" else "way"
    rm_name = {r: f"RM_TO_{topo.name[r].upper()}_OUT" for r in ("way", "alt")}
    eth = [("eth1", f"{topo.ip[('dst', lo_role)]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', hi_role)]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["dst"], lo, eth, dummies), _frr_header(topo.name["dst"])]
    body.append(f"interface lo\n ip address {lo}/32\n!\n")
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', lo_role)]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('dst', hi_role)]}{_LINK_MASK}"))
    body.append(f"interface dum0\n ip address {topo.customer_ip}/24\n!\n")
    # Outbound prepend maps, in physical-slot order. Toward `way`: plain permit (no
    # prepend) baseline; toward `alt`: prepend dst's own ASN `pre_depth` times.
    prepend_of = {"way": [], "alt": [_prepend_line(dst_asn, pre)]}
    for r in (lo_role, hi_role):
        lines = "".join(l + "\n" for l in prepend_of[r])
        body.append(f"route-map {rm_name[r]} permit 10\n" + lines + "!\n")
    body.append(f"router bgp {dst_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[(lo_role, 'dst')]} remote-as {p.asn[lo_role]}\n")
    body.append(f" neighbor {topo.ip[(hi_role, 'dst')]} remote-as {p.asn[hi_role]}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    for r in (lo_role, hi_role):
        body.append(f"  neighbor {topo.ip[(r, 'dst')]} route-map {rm_name[r]} out\n")
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
# The change: an OUTBOUND as-path-prepend edit on dst (the foreign customer AS).
# change_target = dst. src is byte-identical pre and post.
# --------------------------------------------------------------------------- #
def _rm_name(topo: _Topo, role: str) -> str:
    """The outbound prepend route-map name toward an upstream role -- named after that
    upstream's (swapped) NODE NAME, so the name carries no waypoint/bypass label info."""
    return f"RM_TO_{topo.name[role].upper()}_OUT"


def _apply_change(topo: _Topo) -> str:
    effect = topo.spec.effect
    pre = topo.spec.pre_depth
    dst_asn = topo.params.asn["dst"]
    before = _dst_config(topo)

    if effect == "bypass":
        # Add an outbound prepend toward `way` long enough to make the via-way AS_PATH
        # STRICTLY longer than the via-alt path. via-alt = 1 (own AS at upstream) +
        # pre (dst's prepend). via-way must exceed it: prepend dst's ASN (pre + 1)
        # times toward way -> via-way = 1 + (pre + 1) = pre + 2 > pre + 1. Strict.
        bypass_times = pre + 1
        rm = _rm_name(topo, "way")
        old = f"route-map {rm} permit 10\n!\n"
        new = (
            f"route-map {rm} permit 10\n"
            f"{_prepend_line(dst_asn, bypass_times)}\n!\n"
        )
    else:  # no_op
        # Extend the ALREADY-LONGER prepend toward `alt` (the losing path) by one more
        # dst-ASN hop. via-alt grows from (1 + pre) to (1 + pre + 1); via-way stays 1.
        # way is still strictly shorter -> the winner does not move -> empty GT.
        rm = _rm_name(topo, "alt")
        old = (
            f"route-map {rm} permit 10\n"
            f"{_prepend_line(dst_asn, pre)}\n!\n"
        )
        new = (
            f"route-map {rm} permit 10\n"
            f"{_prepend_line(dst_asn, pre + 1)}\n!\n"
        )

    if old not in before:
        raise RuntimeError(
            f"change anchor {old!r} not found for {topo.spec.dims_label()} on dst "
            f"(seed render drift)"
        )
    after = before.replace(old, new, 1)
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
# phrased the SAME way: the prose names only WHICH outbound route-map on dst gets the
# as-path-prepend edit, never whether the best path moves.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    effect = topo.spec.effect
    dst = topo.name["dst"]
    # the edited route-map's NAME is whichever upstream's (swapped) node name applies this
    # seed -> the name carries no waypoint/bypass label info.
    which = _rm_name(topo, "way") if effect == "bypass" else _rm_name(topo, "alt")
    return (
        f"On `{dst}` (AS{topo.params.asn['dst']}, the customer-origin AS), edit the "
        f"outbound eBGP route-map `{which}` to add/extend a `set as-path prepend` "
        f"clause (an AS_PATH adjustment on the advertisement toward one upstream). "
        f"See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tune outbound path advertisement for "
    "this destination."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: FarAsPrependSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + all four loopbacks (negative controls).
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
            note=f"far-as prepend quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_far_as_prepend_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    node_rng = random.Random(f"far_as_prepend_nodes_{seed}")
    nodes = [src, way, alt, dst]
    node_rng.shuffle(nodes)

    return Scenario(
        name=name,
        nodes=nodes,
        pre_configs=pre,
        change_target=dst,   # the DECISIVE edit lives in the foreign customer AS
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
def generate_far_as_prepend_instance(
    seed: int, spec: Optional[FarAsPrependSpec] = None
) -> Scenario:
    """Emit ONE Family-2 far_as_prepend instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[FarAsPrependSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_far_as_prepend_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_far_as_prepend_suite(
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
