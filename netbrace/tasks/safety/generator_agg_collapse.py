"""Family-3 generator — AGGREGATE-SUMMARY COLLAPSE (the `agg_collapse` mechanism):
a counterintuitive INVERSE-LPM quiet reroute where a "table-hygiene" aggregate on the
inspection-path border SUPPRESSES a steering more-specific /25, so the source's
longest-prefix-match silently falls back to a covering /24 whose best path leaves the
inspection node — with ZERO session, prefix-loss, or reachability surface.

This is a Family-3 (route-visibility / projection) mechanism, structurally distinct from
the Family-1 recursive-underlay-displacement generators (igp-metric / igp-summary /
redistribute-ad / nexthop-elim — those move a BGP next-hop's IGP resolution) and from the
Family-2 comparator wedges (lp / med / as-path attribute flips on the /24 itself). Here
NOTHING about the /24's best path is touched; the decisive change is the DISAPPEARANCE of
a more-specific /25 from the source's table — an LPM (RFC 1812 §5.2.4.3 / longest-match
forwarding) fall-back, not a best-path attribute comparison. The /25 vanishing is the
operator's INTENDED "summarize / clean up the table" outcome and is therefore NOT a loud
withdrawal (it is EXCLUDED from the D2 watch set per the build doctrine); the customer
destination stays reachable the whole time via the covering /24.

Mechanism (RFC 4632 §5.3 de-aggregation/aggregation + RFC 1812 longest-prefix-match):
``dst`` (the customer AS) originates the covering customer /24 and dual-homes it to BOTH
upstreams (``way`` and ``alt``). The inspection-path upstream ``way`` ALSO originates a
steering MORE-SPECIFIC /25 that covers the customer host (a common inbound-TE technique:
advertise a more-specific over the path you want host traffic to take). ``src`` peers
eBGP with both upstreams and reaches the customer host by LPM.

  * PRE: ``src`` learns the /25 ONLY via ``way`` (single path) and the /24 via BOTH
    upstreams; an inbound LOCAL_PREF preference on the ``alt`` session makes the /24's
    best path the OFF-waypoint ``alt`` egress (a strict LP gap, decided ABOVE router-id).
    LPM at ``src``: the customer host matches the /25, so host traffic transits ``way``.
    The waypoint intent holds.
  * DIFF (bypass): on the aggregating border ``way``, add
    ``aggregate-address <customer/24> summary-only`` — a routine "table hygiene" cleanup.
    ``summary-only`` SUPPRESSES advertisement of ``way``'s contributing more-specific
    (the steering /25) to ``src`` (RFC 4632 §5.3; FRR ``bgp.rst`` aggregate-address). The
    /24 aggregate ``way`` now originates is LP-100, still losing to ``alt``'s LP-200 /24.
  * POST: ``src`` no longer has the /25; LPM falls back to the /24, whose best path is the
    ``alt`` egress, so the customer host now transits ``alt`` — it BYPASSES ``way`` while
    staying reachable via the /24.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): an aggregate-address edit never
resets the BGP FSM (RFC 4271 §8), so D1=∅. The /24 stays BEST and installed at ``src``
(only the host's LPM resolution moves), so D2=∅ on the WATCHED set (the /24 + loopbacks
all survive; the /25's intended suppression is excluded from the watch set so it is NOT a
loud D2 withdrawal). ``alt`` delivers the host exactly as ``way`` did, so D3=∅, D7=∅. The
/24's best path is a STRICT LP gap (200 > 100) in BOTH snapshots and the /25 is a single
path PRE, so there is exactly one best path each time (no equal-cost ECMP tie,
maximum-paths default 1) → D5=∅ and the oracle is byte-identical. The strict gap is
decided at the LOCAL_PREF step, ABOVE the nondeterministic router-id/age steps (the
documented Batfish ECMP-multipath trap), which keeps it deterministic AND D5 empty.

Topology (4 nodes, ALL eBGP, distinct ASNs, directly-connected /30 next-hops, NO
statics)::

           inbound LP route-map on src toward alt (the /24 discriminator)
        +----------------------------------------------------+
        |                                                    |
      src ---/30(eBGP)--- way (AS_way) ---/30(eBGP)--- dst   (the WAY / inspection path)
   (AS_src) |             [orig /25,         |
            |              the KNOB]          |   customer /24 (orig by dst,
            +---/30(eBGP)--- alt (AS_alt) ---/30(eBGP)---+    dual-homed way & alt)

  * src is AS_src; it eBGP-peers DIRECTLY (over the /30 link IP, no update-source, no
    multihop) with both way (AS_way) and alt (AS_alt). eBGP next-hops are directly
    connected, so the customer routes resolve with NO static route anywhere.
  * way and alt are distinct upstream ASes; each eBGP-peers with dst (AS_dst) over a
    directly-connected /30. dst originates the customer /24 on a connected dummy host.
  * way ALSO originates the steering /25 (on its own connected dummy host) — this is the
    only more-specific in the design, advertised only over the way path. The aggregate
    on way (the change) has a real BGP contributor (the /25), so Batfish generates the
    aggregate (Batfish only generates a BGP aggregate when a contributor exists).
  * src applies an inbound LOCAL_PREF preference on the ALT session (RM_ALT_IN,
    set local-preference 200) so the /24's best path is alt (a strict gap above
    router-id). No policy touches the /25. The change edits NOTHING on src — it is a
    one-stanza aggregate-address ADD on way.

Structural axes (each a genuinely distinct config-reading task or a calibration control —
NOT a clone):

  * granularity ∈ {ms25, ms26} — the steering more-specific is a /25 or a /26 of the
    customer /24. Both are suppressed identically by the SAME ``summary-only`` aggregate,
    but they force the reader to compute a DIFFERENT longest-prefix-match boundary (which
    length the host falls back FROM) — an off-by-one LPM reasoning task, not a clone. (We
    deliberately do NOT offer a ``suppress-map`` form: on the pinned Batfish digest
    ``aggregate-address ... suppress-map`` is PARSED but its selective suppression is NOT
    modeled — the contributing more-specific survives, so the mechanism would silently
    fail to fire. Verified live 2026-06-15; ``summary-only`` blanket suppression IS
    modeled and is the gradeable form. See the module-validation note.)

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : ``aggregate-address <c/24> summary-only`` SUPPRESSES the steering
        more-specific, so src's LPM falls back to the /24. D4+D10 fire;
        D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME KIND of edit (an aggregate-address on the SAME border ``way``)
        but a BARE ``aggregate-address <c/24>`` with NO ``summary-only`` keyword — it
        originates the /24 aggregate but does NOT suppress the steering more-specific, so
        it survives at src, LPM still uses it, the host still transits way. Ground truth
        COMPLETELY EMPTY across ALL dimensions — the calibration trap (the ``summary-only``
        keyword is the entire difference; the prose is the same shape).

That is 2 granularities × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp / igp_metric):
the four ASNs (4-byte private range), the loopback block, the link /30 supernet, the
customer /24, and the node base name are all drawn deterministically from the seed. Same
seed ⇒ byte-identical instance; different seed ⇒ a novel instance even for this public
mechanism.

Determinism contract (oracle_determinism_spec class STATIC-DET): the /24 best path is a
STRICT LOCAL_PREF gap in both snapshots and the /25 is a single path PRE — exactly one
best path at src each time, no equal-cost ECMP tie, maximum-paths default 1. Router-ids
are pinned to the (randomized) loopbacks. D4 is scored by ExtendedOracle._waypoint_diff
as the all-traces-transit invariant; D10 by the matching kind="waypoint" IntentInvariant
on the HOST /32 (the LPM-resolved object whose match length moves /25→/24). NO static
routes (all eBGP, directly-connected next-hops) ⇒ no recursive-next-hop artifact.

Public API mirrors generator_lp:
    generate_agg_collapse_suite(n, base_seed=...)        -> list[Scenario]
    generate_agg_collapse_all_combos(seed=...)           -> list[Scenario]
    generate_agg_collapse_instance(seed, spec=None)      -> Scenario
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
# Steering more-specific length per granularity axis value. /25 and /26 are both
# suppressed identically by `summary-only`, but force a different LPM fall-back boundary.
GRANULARITY_VALUES = ("ms25", "ms26")
EFFECT_VALUES = ("bypass", "no_op")

_MS_LEN = {"ms25": 25, "ms26": 26}

AXES = {
    "granularity": GRANULARITY_VALUES,
    "effect": EFFECT_VALUES,
}

# LOCAL_PREF on src's inbound from each upstream. ALT strictly beats WAY for the /24, so
# the /24's best path is the off-waypoint alt egress in BOTH snapshots (the strict gap is
# decided ABOVE router-id => deterministic, no ECMP tie). WAY keeps the eBGP default (no
# inbound LP set => 100); ALT is raised to 200.
_LP_ALT = 200


@dataclass(frozen=True)
class AggCollapseSpec:
    """A point in the Family-3 agg-collapse generator space (axis tuple, pre-random)."""

    granularity: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.granularity}-{self.effect}"


def enumerate_specs() -> list[AggCollapseSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[AggCollapseSpec] = []
    for granularity in GRANULARITY_VALUES:
        for effect in EFFECT_VALUES:
            out.append(AggCollapseSpec(granularity, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). FOUR DISTINCT ASNs (src/way/alt/dst); a band clear
# of every other generator's band so a generated instance never collides.
_ASN_LO, _ASN_HI = 4_200_500_000, 4_200_599_999

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

    asn: dict[str, int]      # role -> ASN (roles: src, way, alt, dst)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name: dict[str, str]     # role -> randomized node name string


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

    return _Params(asn=asn, loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name=name)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: AggCollapseSpec
    name: dict[str, str]
    loopback: dict[str, str]
    ip: dict[tuple[str, str], str]
    customer_prefix: str       # the covering /24 "<net>.0/24"
    customer_ip: str           # the customer host inside the /25, "<net>.1"
    steering_prefix: str       # the steering more-specific "<net>.0/25"
    steering_ip: str           # a host inside the /25 for way's connected origin


def _build_topo(spec: AggCollapseSpec, params: _Params) -> _Topo:
    name = dict(params.name)
    rid_index = {"src": 1, "way": 2, "alt": 3, "dst": 4}
    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets carved from the link block:
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

    ms_len = _MS_LEN[spec.granularity]
    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"        # host in the LOW more-specific
    steering_prefix = f"{params.customer_net}.0/{ms_len}"  # the steering more-specific
    steering_ip = f"{params.customer_net}.2"         # a distinct host way owns in the MS

    return _Topo(params=params, spec=spec, name=name, loopback=loopback, ip=ip,
                 customer_prefix=customer_prefix, customer_ip=customer_ip,
                 steering_prefix=steering_prefix, steering_ip=steering_ip)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1). All eBGP, directly-
# connected /30 peers, NO static routes anywhere.
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


def _src_config(topo: _Topo) -> str:
    """src: eBGP to way + alt (directly-connected /30s). An inbound LOCAL_PREF preference
    on the ALT session makes the /24's best path alt (a strict gap above router-id). NO
    policy touches the /25. NOTHING on src is edited by the change."""
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}"))
    # The /24 discriminator: raise LOCAL_PREF for everything from alt -> alt wins the /24
    # (and would win the /25 too, but src only ever LEARNS the /25 from way, single path).
    body.append(f"route-map RM_ALT_IN permit 10\n set local-preference {_LP_ALT}\n!\n")
    body.append(f"router bgp {p.asn['src']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  neighbor {topo.ip[('alt', 'src')]} route-map RM_ALT_IN in\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _way_config(topo: _Topo, *, aggregate: Optional[list[str]] = None) -> str:
    """way: the inspection-path upstream + the aggregating border. eBGP to src and to dst.
    Originates the steering more-specific on a connected dummy host; re-advertises dst's
    /24. The change ADDS an aggregate-address stanza here. ``aggregate`` is the list of
    address-family lines to insert (the change), or None for the baseline."""
    p = topo.params
    lo = topo.loopback["way"]
    ms_len = _MS_LEN[topo.spec.granularity]
    eth = [("eth1", f"{topo.ip[('way', 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('way', 'dst')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.steering_ip}/{ms_len}")]
    body = [_iface_header(topo.name["way"], lo, eth, dummies), _frr_header(topo.name["way"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('way', 'src')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('way', 'dst')]}{_LINK_MASK}"))
    body.append(_plain_iface("dum0", f"{topo.steering_ip}/{ms_len}"))
    body.append(f"router bgp {p.asn['way']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('src', 'way')]} remote-as {p.asn['src']}\n")
    body.append(f" neighbor {topo.ip[('dst', 'way')]} remote-as {p.asn['dst']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.steering_prefix}\n")   # the steering /25 (way's own)
    for line in (aggregate or []):
        body.append(line + "\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _alt_config(topo: _Topo) -> str:
    """alt: the bypass upstream. eBGP to src and to dst, no policy, no /25, no statics.
    Re-advertises dst's covering /24 only."""
    p = topo.params
    lo = topo.loopback["alt"]
    eth = [("eth1", f"{topo.ip[('alt', 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('alt', 'dst')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["alt"], lo, eth, []), _frr_header(topo.name["alt"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
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
    """dst: the customer AS, eBGP to way + alt, originates the covering customer /24 + lo.
    Does NOT originate the /25 (that is way's steering more-specific)."""
    p = topo.params
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["dst"], lo, eth, dummies), _frr_header(topo.name["dst"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}"))
    body.append(_plain_iface("dum0", f"{topo.customer_ip}/24"))
    body.append(f"router bgp {p.asn['dst']}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'dst')]} remote-as {p.asn['way']}\n")
    body.append(f" neighbor {topo.ip[('alt', 'dst')]} remote-as {p.asn['alt']}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(f"  network {topo.customer_prefix}\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: _way_config(topo),          # baseline: no aggregate stanza
        topo.name["alt"]: _alt_config(topo),
        topo.name["dst"]: _dst_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change: an aggregate-address ADD on the aggregating border ``way``. Per (form,
# effect). bypass forms SUPPRESS the steering /25 (LPM falls back to the /24); no_op forms
# add an aggregate that does NOT suppress the /25 (the same KIND of edit, genuinely inert).
# --------------------------------------------------------------------------- #
def _aggregate_lines(topo: _Topo) -> list[str]:
    """Return the address-family aggregate-address line(s) the change adds on ``way``.

    bypass: ``aggregate-address <c/24> summary-only`` (suppresses the steering MS — the
            Batfish-modeled blanket suppression).
    no_op : a bare ``aggregate-address <c/24>`` (originates the /24 aggregate but does NOT
            suppress the steering MS — the ``summary-only`` keyword is the whole diff).
    """
    c24 = topo.customer_prefix
    if topo.spec.effect == "bypass":
        return [f"  aggregate-address {c24} summary-only"]
    return [f"  aggregate-address {c24}"]


def _apply_change(topo: _Topo) -> str:
    """Return the unified diff applied to ``way`` for this (granularity, effect)."""
    before = _way_config(topo, aggregate=None)
    after = _way_config(topo, aggregate=_aggregate_lines(topo))
    if before == after:
        raise RuntimeError(
            f"agg_collapse change for {topo.spec.dims_label()} is a no-diff (render drift)"
        )
    return _unified(before, after, topo.name["way"])


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
# phrased the SAME way: the prose names only WHICH aggregate-address stanza is added on
# WHICH border, never whether the more-specific is suppressed or the path moves. "aggregate"
# / "summary-only" / "suppress-map" / "prefix-list" / "more-specific" are config-construct
# words (they name what is edited) and are allowed; "falls back", "bypasses", "still
# reachable", "no longer", "nothing changes" are OUTCOME leaks and appear NOWHERE.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    way = topo.name["way"]
    c24 = topo.customer_prefix
    clause = " summary-only" if topo.spec.effect == "bypass" else ""
    return (
        f"On `{way}` (AS{topo.params.asn['way']}), add a single "
        f"`aggregate-address {c24}{clause}` stanza under the BGP IPv4 unicast "
        f"address-family — a routine table-hygiene/summarization edit. See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer host {host} MUST transit the inspection "
    "node `{way}`. The customer space {cust} MUST remain reachable. The operator's "
    "stated goal for the change is to summarize / tidy the advertised table on the "
    "border."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: AggCollapseSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    patch = _apply_change(topo)

    src, way, alt, dst = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: the COVERING /24 + all loopbacks (negative controls). CRITICAL: the
    # steering /25 is DELIBERATELY EXCLUDED — its suppression is the operator's intended
    # outcome and must NOT count as a loud D2 withdrawal (build doctrine). The /24 and the
    # loopbacks all SURVIVE post-change, so D2 = ∅.
    watched = [f"{topo.loopback[r]}/32" for r in _ROLES] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (via the /24/alt).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer HOST must transit `way`. Probe the /32 host (the
    # LPM-resolved object whose match length moves /25 -> /24 across the diff).
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint restated as a kind="waypoint" IntentInvariant
    # so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"agg-collapse inverse-LPM: src->{cust_host} must transit {way} "
                 f"(LPM via the steering {topo.steering_prefix} pre, the {cust} post).",
        )
    ]

    name = f"gen_agg_collapse_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, host=cust_host, way=way, cust=cust)

    return Scenario(
        name=name,
        nodes=[src, way, alt, dst],
        pre_configs=pre,
        change_target=way,
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
def generate_agg_collapse_instance(
    seed: int, spec: Optional[AggCollapseSpec] = None
) -> Scenario:
    """Emit ONE Family-3 agg-collapse instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[AggCollapseSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_agg_collapse_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]


def generate_agg_collapse_suite(
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
