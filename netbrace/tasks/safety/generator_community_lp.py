"""Family-2 generator — COMMUNITY-DRIVEN LOCAL_PREF SECOND-ORDER PATH-SHIFT (the
`community_lp` mechanism): a BGP COMMUNITY edit on the upstream's OUTBOUND policy
re-arms (or disarms) a LATENT, UNCHANGED community→LOCAL_PREF match on the receiver,
flipping the receiver's best path off the inspection waypoint — WITHOUT the
LOCAL_PREF token EVER appearing in the diff.

This is the Family-2 second-order sibling of the Family-1 `lp_waypoint`/`igp_metric`
quiet-half mechanisms (temporary/frozen_quiet_half_scenario_set.md). It is
structurally distinct from the first-order `lp_waypoint` (whose diff edits the
LOCAL_PREF value directly — a construct every model catches) and from the
recursive-underlay Family-1 set (whose decisive change lives in the IGP). Here the
decisive change is a `set community` edit on the ADVERTISER (`way`), and the
LOCAL_PREF that actually moves the best path is set by an UNCHANGED inbound route-map
on the RECEIVER (`src`) that conditions on the community tag. The reader must connect
two configs across two devices — the community the advertiser attaches, and the
community-list the receiver matches — to see that stripping/rewriting the tag silently
drops the receiver's latent LOCAL_PREF bump.

Mechanism (RFC 1997 BGP COMMUNITIES + RFC 4271 §9.1.1 step 2 — "prefer the path with
the higher LOCAL_PREF"): `way` re-advertises the customer /24 to `src` carrying a
community tag C on its OUTBOUND policy (`set community C`). `src` has an UNCHANGED
inbound route-map on the `way` session that does `match community <C-list> ->
set local-preference HIGH`; the `alt` session takes the default LOCAL_PREF. So in the
PRE state the way path carries C, src's latent match fires, way's LOCAL_PREF is
strictly HIGHER than alt's, and src->customer transits the inspection node `way`.

  * PRE : way's outbound tags the customer route with C; src's inbound matches C and
    raises that path's LOCAL_PREF to HIGH (strictly > alt's default) -> way wins.
  * DIFF (bypass): REMOVE or REWRITE the `set community` on way's OUTBOUND so tag C is
    no longer attached. THE LP TOKEN IS NEVER IN THE DIFF — it is in src's UNCHANGED
    inbound map. With C gone, src's latent community match no longer fires, way's
    LOCAL_PREF falls back to the default, and the default-LP alt path wins.
  * POST: best path re-resolves to `alt`, and src->customer silently bypasses `way`.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): a community / outbound-policy
edit never resets the BGP FSM (RFC 4271 §8: Established exits only on
NOTIFICATION/hold-timer/TCP teardown), so D1=∅. The /24 stays BEST and installed in
every RIB (only its winning copy's egress moves), so D2=∅; `alt` delivers exactly as
`way` did, so D3=∅, D7=∅. A STRICT (non-equal) LOCAL_PREF gap in BOTH snapshots
(HIGH vs default pre; default vs HIGH-on-alt... no — see below) means exactly one best
path each time (maximum-paths default 1, no equal-cost ECMP tie), so D5=∅ and the
oracle is byte-identical. The strict LP gap is decided at RFC 4271 step 2 — ABOVE the
nondeterministic router-id/age steps (the documented Batfish ECMP-multipath trap) —
which keeps the decision deterministic AND D5 empty.

Strict-LP construction in BOTH snapshots:
  * PRE : LP(way)=HIGH (community match fired) > LP(alt)=DEFAULT(100). Strict gap.
  * POST: LP(way)=DEFAULT(100) (tag stripped, match silent) ; LP(alt)=DEFAULT(100).
    A bare DEFAULT/DEFAULT tie would fall through to AS_PATH/MED/router-id and risk a
    D5 ECMP tie — so the alt session ALSO carries an UNCHANGED inbound LP bump (a
    SMALLER one, LP_MID, strictly between DEFAULT and HIGH and ALWAYS armed because it
    is unconditional). PRE: HIGH(way) > LP_MID(alt) -> way wins, strict. POST:
    LP_MID(alt) > DEFAULT(way) -> alt wins, strict. Exactly one best path in each
    snapshot at the LOCAL_PREF step — no tie, no ECMP, D5=∅, deterministic.

Topology (4 nodes, ALL eBGP, distinct ASNs, directly-connected next-hops — the
generator_lp shape; NO OSPF, NO recursion, NO static routes)::

           inbound route-maps (the LATENT LP knobs, UNCHANGED) on src per upstream
        +----------------------------------------------------+
        |                                                    |
      src ---/30--- way (AS_way) ---/30(eBGP)--- dst   (the WAY / inspection path)
   (AS_src) |                                      |
            |                                      |   customer /24
            +---/30--- alt (AS_alt) ---/30(eBGP)---+   (originated by dst,
                                                       dual-homed to way & alt)

  * src is AS_src; it eBGP-peers DIRECTLY (over the /30 link IP, no update-source, no
    multihop) with both way (AS_way) and alt (AS_alt).
  * way and alt are distinct upstream ASes; each eBGP-peers with dst (AS_dst) over a
    directly-connected /30. dst originates the customer /24 on a dummy host.
  * The eBGP next-hop on each received route is the DIRECTLY-CONNECTED upstream /30 IP,
    so it resolves with NO static route (the generator_lp re-home doctrine).
  * way applies an OUTBOUND route-map toward src (RM_TO_SRC_OUT) that tags the
    customer route with community C (`set community C`). alt applies its own OUTBOUND
    map (RM_TO_SRC_OUT) tagging with a DIFFERENT community D (so a no_op edit has a
    real construct to touch on alt). Both upstreams `send-community`.
  * src applies INBOUND route-maps (RM_UPLINK1_IN on way, RM_UPLINK2_IN on alt). The
    way map matches C-list and raises LOCAL_PREF to HIGH; the alt map sets LOCAL_PREF
    to LP_MID unconditionally. THESE ARE NEVER EDITED — the change lives on way only.

Structural axes (each a genuinely distinct config-reading task or a calibration
control — NOT a clone):

  * knob ∈ {strip_tag, rewrite_tag} — two DIFFERENT community edits on way's outbound,
    each forcing the reader to parse a different construct:
      - strip_tag  : the change DELETES the `set community C` line from way's outbound
        map entirely (a line-removal edit). C is no longer attached; src's latent
        match goes silent.
      - rewrite_tag: the change REWRITES the `set community` VALUE on way's outbound
        from C to an UNRELATED tag C2 that src's community-list does NOT permit (a
        value edit). C is no longer attached; same downstream consequence, different
        device construct to read (a value swap vs a line deletion).

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the edit actually removes tag C from the WAY path. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of community edit applied to the ALT path's outbound
        (strip / rewrite alt's tag D), where it does NOT move the installed best path
        (way still carries C, src's latent match still fires, way still wins by HIGH >
        LP_MID). Ground truth is COMPLETELY EMPTY across ALL dimensions — the
        calibration trap (the model must predict an empty blast radius). The prose is
        indistinguishable in style from a bypass edit; only careful best-path /
        community-flow reasoning separates them.

That is 2 knobs × 2 effects = 4 structural combos × seeds. NOTE: for no_op the change
device is ALT (the edit that is provably inert is the one on the LOSING/irrelevant
path), so ``change_target`` = way for bypass and alt for no_op — both are upstream
advertisers, the edit is the same KIND (a `set community` strip/rewrite on an outbound
map), and the prose names only which router/map/value is touched.

Per-seed randomization (contamination control, exactly like generator_lp): the four
ASNs, the loopback block, the link /30 supernet, the customer /24, the node base name,
AND the community VALUES (C, D, C2) are all drawn deterministically from the seed.
Same seed ⇒ byte-identical instance; different seed ⇒ a novel instance even for this
public mechanism.

Per-seed GATE (build-time): the bypass diff is asserted to actually STRIP tag C from
way's post-config (C absent from way's post but present in way's pre), so a render
drift that left C in place — silently turning a bypass into a no-op — fails loud.

Determinism contract (oracle_determinism_spec_v1.md class 5, STATIC-DET): every
best-path decision is STRICT at the LOCAL_PREF step in both snapshots (HIGH>LP_MID pre,
LP_MID>DEFAULT post) — exactly one best path at src in each snapshot, no equal-cost
ECMP tie, maximum-paths default 1. Router-ids are pinned to the (randomized)
loopbacks. D4 is scored by ExtendedOracle._waypoint_diff as the all-traces-transit
invariant; D10 by the matching kind="waypoint" IntentInvariant. NO static routes ⇒ no
recursive-next-hop artifact.

Public API mirrors generator_lp:
    generate_community_lp_suite(n, base_seed=...)       -> list[Scenario]
    generate_community_lp_all_combos(seed=...)          -> list[Scenario]
    generate_community_lp_instance(seed, spec=None)     -> Scenario
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
KNOB_VALUES = ("strip_tag", "rewrite_tag")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# LOCAL_PREF values for the latent (UNCHANGED) inbound maps on src. HIGH is the
# community-conditioned bump on the way session; LP_MID is the unconditional bump on
# the alt session. STRICT ordering DEFAULT(100) < LP_MID < HIGH so:
#   PRE  : LP(way)=HIGH  > LP(alt)=LP_MID  -> way wins (community match fired)
#   POST : LP(way)=DEFAULT < LP(alt)=LP_MID -> alt wins (tag stripped, match silent)
# Both snapshots decide at the LOCAL_PREF step with a strict gap (no ECMP tie, D5=∅).
_LP_DEFAULT = 100
_LP_MID = 150
_LP_HIGH = 300


@dataclass(frozen=True)
class CommunityLpSpec:
    """A point in the Family-2 community_lp generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[CommunityLpSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[CommunityLpSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(CommunityLpSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). FOUR DISTINCT ASNs (src/way/alt/dst) so a
# generated instance never collides with the hand-authored 65000 family and every AS
# is genuinely external to every other. Distinct block from generator_lp/igp_metric.
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
    comm_c: str              # community tag the WAY path carries + src matches (C)
    comm_d: str              # community tag the ALT path carries (D, src ignores)
    comm_c2: str             # the rewrite target (C2, NOT in src's community-list)
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

    # Three DISTINCT community VALUES in the 16-bit:16-bit space (RFC 1997). The
    # global-admin half is drawn per-seed; the local-admin halves are distinct fixed
    # tags so C, D, C2 never collide. C = the matched tag, D = alt's (ignored) tag,
    # C2 = the rewrite target (deliberately NOT in src's community-list).
    ga = rng.randint(1, 65000)
    comm_c = f"{ga}:{rng.randint(100, 199)}"
    comm_d = f"{ga}:{rng.randint(200, 299)}"
    comm_c2 = f"{ga}:{rng.randint(300, 399)}"

    # Per-seed ROLE->POSITION swap (the positional-leak fix): drawn LAST so every
    # addressing/community draw above is byte-identical to before; it only decides
    # which PHYSICAL slot the waypoint role `way` vs the bypass role `alt` occupies.
    swap = _rp.draw_swap(rng)

    return _Params(asn=asn, loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name=name,
                   comm_c=comm_c, comm_d=comm_d, comm_c2=comm_c2, swap=swap)


# --------------------------------------------------------------------------- #
# Topology builder: src dual-homed (eBGP) to way + alt, each eBGP to dst.
# Links, fixed order (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    """A concrete, addressed all-eBGP topology for one instance."""

    params: _Params
    spec: CommunityLpSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str


def _build_topo(spec: CommunityLpSpec, params: _Params) -> _Topo:
    # Per-seed swap exchanges the PHYSICAL slot (loopback octet, name suffix, link-IP
    # carving, node order) of the waypoint role `way` and the bypass role `alt`, so the
    # edited node's identity/position carries ZERO trap/no_op label information.
    rid_index = _rp.swapped_rid_index(
        {"src": 1, "way": 2, "alt": 3, "dst": 4}, params.swap, ("way", "alt"))
    name = _rp.swapped_names(dict(params.name), params.swap, ("way", "alt"))
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved from the link block. The way-side vs alt-side link
    # blocks are assigned by the (swapped) physical slot so the waypoint role's link
    # IPs also move per seed: slot-2 role uses base .0/.8, slot-3 role uses base .4/.12.
    lo_role = "way" if rid_index["way"] == 2 else "alt"   # the role on physical slot 2
    hi_role = "alt" if lo_role == "way" else "way"        # the role on physical slot 3
    ip: dict[tuple[str, str], str] = {
        ("src", lo_role): addr(1), (lo_role, "src"): addr(2),
        ("src", hi_role): addr(5), (hi_role, "src"): addr(6),
        (lo_role, "dst"): addr(9), ("dst", lo_role): addr(10),
        (hi_role, "dst"): addr(13), ("dst", hi_role): addr(14),
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


# ---- src: the LATENT (UNCHANGED) inbound LP knobs conditioned on community ---- #
# RM_UPLINK1_IN (way session): match community C-list -> set LOCAL_PREF HIGH; a
#   trailing permit so non-matching routes still pass at default LP.
# RM_UPLINK2_IN (alt session): set LOCAL_PREF LP_MID unconditionally (always armed),
#   strictly between DEFAULT and HIGH. NEITHER MAP IS EVER EDITED.
def _src_config(topo: _Topo) -> str:
    p = topo.params
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name["src"], topo.loopback["src"], eth, [])

    body = [ib, _frr_header(topo.name["src"]), fb]
    # The community-list src matches against (only C is permitted; D and C2 are not).
    body.append(f"bgp community-list standard CL_MATCH permit {p.comm_c}\n!\n")
    # Inbound map on the way session: community-conditioned LP bump (the LATENT knob).
    body.append(
        "route-map RM_UPLINK1_IN permit 10\n"
        " match community CL_MATCH\n"
        f" set local-preference {_LP_HIGH}\n!\n"
        "route-map RM_UPLINK1_IN permit 20\n!\n"
    )
    # Inbound map on the alt session: unconditional LP_MID (always armed, strict gap).
    body.append(
        "route-map RM_UPLINK2_IN permit 10\n"
        f" set local-preference {_LP_MID}\n!\n"
    )
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


# ---- way / alt: eBGP to src + dst; OUTBOUND community tag toward src ---------- #
# way tags with C (the matched tag); alt tags with D (src ignores it). send-community
# is enabled on the src-facing session so the tag actually crosses the eBGP edge.
def _upstream_config(topo: _Topo, role: str) -> str:
    p = topo.params
    tag = topo.params.comm_c if role == "way" else topo.params.comm_d
    eth = [("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}")]
    ib, fb = _ifaces_intf_text(topo.name[role], topo.loopback[role], eth, [])
    body = [ib, _frr_header(topo.name[role]), fb]
    # OUTBOUND map toward src: attach this upstream's community tag to all routes.
    body.append(
        "route-map RM_TO_SRC_OUT permit 10\n"
        f" set community {tag}\n!\n"
    )
    body.append(f"router bgp {p.asn[role]}\n")
    body.append(f" bgp router-id {topo.loopback[role]}\n")
    body.append(f" neighbor {topo.ip[('src', role)]} remote-as {p.asn['src']}\n")
    body.append(f" neighbor {topo.ip[('dst', role)]} remote-as {p.asn['dst']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback[role]}/32\n")
    body.append(f"  neighbor {topo.ip[('src', role)]} send-community\n")
    body.append(f"  neighbor {topo.ip[('src', role)]} route-map RM_TO_SRC_OUT out\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _dst_config(topo: _Topo) -> str:
    p = topo.params
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    ib, fb = _ifaces_intf_text(topo.name["dst"], topo.loopback["dst"], eth, dummies)
    body = [ib, _frr_header(topo.name["dst"]), fb]
    body.append(f"router bgp {p.asn['dst']}\n")
    body.append(f" bgp router-id {topo.loopback['dst']}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {topo.loopback['dst']}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
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
# The change: a `set community` edit on an upstream's OUTBOUND map. The LP token is
# NEVER touched. bypass edits WAY (strips/rewrites tag C); no_op edits ALT (strips/
# rewrites tag D) where it cannot move the installed best path.
# --------------------------------------------------------------------------- #
def _change_role(spec: CommunityLpSpec) -> str:
    """The device the edit lands on: way for bypass, alt for the inert no_op."""
    return "way" if spec.effect == "bypass" else "alt"


def _apply_change(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    role = _change_role(topo.spec)
    before = _upstream_config(topo, role)
    tag = topo.params.comm_c if role == "way" else topo.params.comm_d

    if knob == "strip_tag":
        # Remove the `set community <tag>` line entirely (a line-removal edit).
        old = (
            "route-map RM_TO_SRC_OUT permit 10\n"
            f" set community {tag}\n!\n"
        )
        new = "route-map RM_TO_SRC_OUT permit 10\n!\n"
    else:  # rewrite_tag
        # Rewrite the community VALUE to C2 (NOT in src's community-list) — a value
        # swap. For the no_op (alt) path the new tag is equally ignored by src.
        new_tag = topo.params.comm_c2
        old = (
            "route-map RM_TO_SRC_OUT permit 10\n"
            f" set community {tag}\n!\n"
        )
        new = (
            "route-map RM_TO_SRC_OUT permit 10\n"
            f" set community {new_tag}\n!\n"
        )

    if old not in before:
        raise RuntimeError(
            f"change anchor not found for {topo.spec.dims_label()} on {role} "
            f"(seed render drift)"
        )
    after = before.replace(old, new, 1)
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
# phrased the SAME way: the prose names ONLY which router's outbound route-map and
# which `set community` value is edited, never whether the best path moves. Naming the
# community construct is allowed (it is what is edited); the LOCAL_PREF / best-path /
# transit consequence appears NOWHERE.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    knob, effect = topo.spec.knob, topo.spec.effect
    role = _change_role(topo.spec)
    node = topo.name[role]
    tag = topo.params.comm_c if role == "way" else topo.params.comm_d
    asn = topo.params.asn[role]
    if knob == "strip_tag":
        return (
            f"On `{node}` (AS{asn}), edit the outbound eBGP route-map "
            f"`RM_TO_SRC_OUT` toward `{topo.name['src']}` to remove its "
            f"`set community {tag}` line (a one-line removal). See the diff."
        )
    # rewrite_tag
    return (
        f"On `{node}` (AS{asn}), edit the outbound eBGP route-map `RM_TO_SRC_OUT` "
        f"toward `{topo.name['src']}` so its `set community` value goes from {tag} "
        f"to {topo.params.comm_c2} (a one-line value edit). See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tidy the BGP community tagging it "
    "advertises for this destination."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: CommunityLpSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)
    change_target = topo.name[_change_role(spec)]

    # Per-seed GATE: a bypass MUST actually strip tag C from way's POST config. Build
    # the post-config for way and assert C is present pre but ABSENT post — so a render
    # drift that left C in place (silently downgrading a bypass to a no_op) fails loud.
    if spec.effect == "bypass":
        way_pre = pre[topo.name["way"]]
        way_post = apply_unified_diff(way_pre, patch)
        c_token = f"set community {params.comm_c}"
        if c_token not in way_pre:
            raise RuntimeError(
                f"bypass gate: tag C ({params.comm_c}) missing from way PRE config "
                f"(seed {seed}, {spec.dims_label()})"
            )
        if c_token in way_post:
            raise RuntimeError(
                f"bypass gate: tag C ({params.comm_c}) still present in way POST "
                f"config — bypass did not strip the tag (seed {seed}, "
                f"{spec.dims_label()})"
            )

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
            note=f"community-driven LP second-order: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_community_lp_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    # Node-list order is randomized per seed (a fresh deterministic stream) so the
    # change_target's INDEX in `nodes` carries no trap/no_op information either.
    node_rng = random.Random(f"community_lp_nodes_{seed}")
    nodes = [src, way, alt, dst]
    node_rng.shuffle(nodes)

    return Scenario(
        name=name,
        nodes=nodes,
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
def generate_community_lp_instance(
    seed: int, spec: Optional[CommunityLpSpec] = None
) -> Scenario:
    """Emit ONE Family-2 community_lp instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[CommunityLpSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_community_lp_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_community_lp_suite(
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
