"""Class-2 generator — more-specific route LEAK (the `leak_ms` mechanism).

This is the SECOND parameterized generator (audit fix K3 — the templated split
previously covered only the Class-1 ipc withdrawal; this adds held-out variants
for the route-leak mechanism so its contamination story, modal-floor, and stats
stand on more than n=1). It turns the verified `leak_ms` MECHANISM — a leaker AS
that originates a more-specific of a victim's prefix so longest-prefix-match pulls
the victim's traffic toward the leaker, while every eBGP session stays ESTABLISHED
and the victim's /24 is never withdrawn from any RIB (D1 = ∅ AND D2 = ∅, the
"session-count and prefix-count give no signal" thesis of Telekom-Malaysia-2015
and Cloudflare-2019) — into N DISTINCT, oracle-gradeable instances over
determinism-SAFE structural axes, with per-seed randomized ASN / addressing /
node-names / victim-prefix as the CONTAMINATION CONTROL (the mechanism is public —
each emitted instance is novel even for the famous incidents).

Relationship to the hand-authored instance (scenario_leak_ms / baseline_leak_ms):
that is the GROUNDED, incident-anchored template this generator is parameterized
FROM. Generated instances set ``provenance="templated"`` (the PRIMARY decontaminated
split); the hand-authored one keeps ``"handauthored"`` (the GROUNDED split). The
mechanism is identical and verified; the generator's value is DIVERSITY of blast
STRUCTURE (which dimensions fire, which flows break) + novel numbering.

STRUCTURAL axes (each genuinely changes the GROUND-TRUTH structure, not just
renames things — verified live, see the module-level VERIFIED-GROUND-TRUTH note):

  * ``leak_kind`` ∈ {ms_blackhole, ms_reroute}:
      - ``ms_blackhole`` — the leaker originates the more-specific(s) backed by a
        DISCARD (Null) static, so it has NO real path to the victim's hosts. LPM
        pulls the victim's traffic to the leaker and DROPS it there. Ground truth:
        D3 reachability_lost (the pulled flow goes DELIVERED->dropped) + D7
        forwarding_anomaly (null_routed AT the leaker); D1 = D2 = ∅. This is the
        current `leak_ms` behaviour (Cloudflare-Jun-2019 congestion/blackhole).
      - ``ms_reroute`` — the leaker originates the more-specific(s) AND actually
        DELIVERS the traffic: it hosts the victim's host address(es) on a connected
        interface inside the leaked /25, so LPM pulls the traffic to the leaker and
        the leaker ACCEPTS it. The flow stays DELIVERED (D3 = ∅, D7 = ∅) — the
        naive reachability check sees NOTHING — yet the victim is BYPASSED: the
        traffic no longer transits the legitimate origin. The damage is a
        waypoint/intent violation (D4 waypoint_violation + D10 te-style waypoint
        IntentViolation: "victim-bound traffic MUST transit the victim AS"). This
        is the hijack/impersonation pattern (Pakistan-YouTube-2008,
        AS7007-style more-specific hijacks) — distinct from the blackhole.
        NOTE: the waypoint invariant requires a declared waypoint NODE; we declare
        the VICTIM as the required transit node for victim-host-bound traffic (an
        oracle-side intent, never shown to the model). D4 is computed via the
        scenario's ``waypoint_intents`` AND restated as a D10 ``waypoint``
        IntentInvariant so both the path dimension and the intent dimension fire.

  * ``leak_scope`` ∈ {low_half, high_half, both_halves}: which /25(s) of the
    victim's /24 the leaker leaks — changes WHICH probe flow breaks/reroutes and
    the exact ground-truth element SET:
      - ``low_half``    — only ``<net>.0/25`` is leaked. The low host (.1) is
        pulled; the high host (.129) stays at the victim (a clean negative
        control, proving the blast is scoped to the leaked half).
      - ``high_half``   — only ``<net>.128/25`` is leaked. Mirror image: the high
        host is pulled, the low host is the negative control.
      - ``both_halves`` — both /25s leaked. Both hosts pulled -> the ground-truth
        element set has BOTH flows (a larger blast than either single half).

That is 2 kinds x 3 scopes = 6 structural combos x infinite seeds.

VERIFIED-GROUND-TRUTH note (live against the pinned batfish/allinone:nethelm,
digest 09817554db90, 2026-06-10; UNIQUE genleak_* networks; each combo 2x
byte-identical). For a representative seed the dimensions that FIRE are:
    ms_blackhole/low_half   -> D3 {transit->lowhost}, D7 {null_routed@leaker:low}
    ms_blackhole/high_half  -> D3 {transit->highhost}, D7 {null_routed@leaker:high}
    ms_blackhole/both_halves-> D3 {both}, D7 {null_routed@leaker: both}
    ms_reroute/low_half     -> D4 {transit->lowhost via victim}, D10 {waypoint same}
    ms_reroute/high_half    -> D4 {transit->highhost via victim}, D10 {waypoint same}
    ms_reroute/both_halves  -> D4 {both}, D10 {both}
In EVERY combo D1 sessions_lost = ∅ and D2 prefixes_lost = ∅ (the /24 stays in
every RIB; the /25s are ADDED). That ∅/∅ pair IS the thesis of this class.

Determinism contract (oracle_determinism_spec_v1.md, class 2 = STATIC-DET): the
change is filtering-free and policy-free (``network`` statements + a discard
static OR a connected interface). The topology is a CHAIN (one origin per prefix,
a single path at the observer), so there is no equal-cost tie to perturb the
chosen path; router-ids are PINNED to the (randomized but fixed-per-seed)
loopbacks. The oracle scores the data-plane SET via traceroute DISPOSITION (D3/D7)
and traceroute TRANSIT (D4/D10), never a chosen-path hash, so every combo is
byte-identical across runs. Each emitted Scenario round-trips and is gradeable by
ExtendedOracle.compute unchanged.
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
LEAK_KIND_VALUES = ("ms_blackhole", "ms_reroute")
LEAK_SCOPE_VALUES = ("low_half", "high_half", "both_halves")

AXES = {
    "leak_kind": LEAK_KIND_VALUES,
    "leak_scope": LEAK_SCOPE_VALUES,
}


@dataclass(frozen=True)
class LeakSpec:
    """A point in the Class-2 generator space (the axis tuple, pre-randomization)."""

    leak_kind: str
    leak_scope: str

    def dims_label(self) -> str:
        return f"{self.leak_kind}-{self.leak_scope}"


def enumerate_specs() -> list[LeakSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[LeakSpec] = []
    for kind in LEAK_KIND_VALUES:
        for scope in LEAK_SCOPE_VALUES:
            out.append(LeakSpec(kind, scope))
    return out


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996): keep clear of the hand-authored 65001/2/3
# family so a generated instance never collides with it. Three DISTINCT ASNs are
# drawn per instance (victim/transit/leaker) — distinctness is the whole point of
# an eBGP chain.
_ASN_LO, _ASN_HI = 4_200_100_000, 4_200_199_999

# Customer-prefix pools (documentation / TEST-NET / RFC-1918 customer space). Each
# instance draws ONE /24 for the VICTIM's protected prefix. {c} is rendered below.
_VICTIM_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1 (kept distinct from the link block, see _draw)
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]
# The leaker's OWN legitimately-served prefix (a negative control), drawn distinct
# from the victim prefix.
_LEAKER_POOLS = [
    "198.18.0.0",    # benchmarking range (RFC 2544) -> /24 base
    "192.88.99.0",   # 6to4 relay anycast (documentation-safe)
    "100.65.{c}.0",  # a different CGNAT /24
    "203.0.114.0",   # TEST-NET-3 adjacent /24
]

# Node base-name pools (string only; topology role is unchanged).
_NAME_POOLS = ["as", "isp", "net", "peer", "carrier", "site"]


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    asn_victim: int
    asn_transit: int
    asn_leaker: int
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.{1,2,3}/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    victim_net: str          # e.g. "198.51.100" (the protected /24 base, no mask)
    leaker_net: str          # e.g. "198.18.0" (the leaker's own /24 base)
    name_victim: str
    name_transit: str
    name_leaker: str


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)
    # three DISTINCT ASNs from the private 4-byte range.
    asns: set[int] = set()
    while len(asns) < 3:
        asns.add(rng.randint(_ASN_LO, _ASN_HI))
    a_victim, a_transit, a_leaker = sorted(asns)

    # loopback /24: 10.<1-250>.<0-250>  (then /32s 10.x.y.{1,2,3})
    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"

    # link /30 supernet: 172.<16-31>.<0-250>  (carve /30s for each link). Use the
    # 172.16/12 block so it never collides with a victim/leaker prefix drawn from
    # the 192.0.2/203.0.113/198.x/100.x pools.
    link_block = (172, rng.randint(16, 31), rng.randint(0, 250))

    # victim + leaker /24 bases (distinct). Render any {c} placeholder.
    vraw = rng.choice(_VICTIM_POOLS).format(c=rng.randint(0, 250))
    victim_net = ".".join(vraw.split(".")[:3])
    # draw the leaker prefix until it differs from the victim's /24.
    while True:
        lraw = rng.choice(_LEAKER_POOLS).format(c=rng.randint(0, 250))
        leaker_net = ".".join(lraw.split(".")[:3])
        if leaker_net != victim_net:
            break

    # three DISTINCT node base names.
    names = rng.sample(_NAME_POOLS, 3)
    return _Params(
        asn_victim=a_victim, asn_transit=a_transit, asn_leaker=a_leaker,
        loop_block=loop_block, link_block=link_block,
        victim_net=victim_net, leaker_net=leaker_net,
        name_victim=names[0], name_transit=names[1], name_leaker=names[2],
    )


# --------------------------------------------------------------------------- #
# Topology builder: a 3-AS eBGP chain, deterministic addressing from the blocks.
#
#   victim (loop .1) === transit (loop .2) === leaker (loop .3)
#       link0 victim<->transit  <b>.<c>.0/30  (victim=.1, transit=.2)
#       link1 transit<->leaker  <b>.<c>.4/30  (transit=.5, leaker=.6)
# eBGP rides the directly-connected /30 link IPs (no update-source, no multihop) —
# the simplest deterministic eBGP, matching baseline_leak_ms.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: LeakSpec
    victim: str
    transit: str
    leaker: str
    nodes: list[str]
    loopback: dict[str, str]           # node -> "x.y.z.N"
    # link IPs
    vt_victim: str                     # victim's IP on victim<->transit
    vt_transit: str                    # transit's IP on victim<->transit
    tl_transit: str                    # transit's IP on transit<->leaker
    tl_leaker: str                     # leaker's IP on transit<->leaker
    victim_prefix: str                 # "<net>/24"
    leaker_prefix: str                 # leaker's own /24
    specific_low: str                  # "<net>.0/25"
    specific_high: str                 # "<net>.128/25"
    # host addresses inside each /25 (probed). The victim hosts BOTH so it is a
    # clean negative-control source/origin in every scope.
    low_host: str                      # "<net>.1"
    high_host: str                     # "<net>.129"


def _build_topo(spec: LeakSpec, params: _Params) -> _Topo:
    victim = f"{params.name_victim}1"
    transit = f"{params.name_transit}2"
    leaker = f"{params.name_leaker}3"
    nodes = [victim, transit, leaker]
    loopback = {
        victim: f"{params.loop_block}.1",
        transit: f"{params.loop_block}.2",
        leaker: f"{params.loop_block}.3",
    }
    b, c, _ = params.link_block
    vt_victim = f"{b}.{c}.0.1"
    vt_transit = f"{b}.{c}.0.2"
    tl_transit = f"{b}.{c}.0.5"
    tl_leaker = f"{b}.{c}.0.6"

    victim_prefix = f"{params.victim_net}.0/24"
    leaker_prefix = f"{params.leaker_net}.0/24"
    specific_low = f"{params.victim_net}.0/25"
    specific_high = f"{params.victim_net}.128/25"
    low_host = f"{params.victim_net}.1"
    high_host = f"{params.victim_net}.129"

    return _Topo(
        params=params, spec=spec, victim=victim, transit=transit, leaker=leaker,
        nodes=nodes, loopback=loopback, vt_victim=vt_victim, vt_transit=vt_transit,
        tl_transit=tl_transit, tl_leaker=tl_leaker, victim_prefix=victim_prefix,
        leaker_prefix=leaker_prefix, specific_low=specific_low,
        specific_high=specific_high, low_host=low_host, high_host=high_host,
    )


# --------------------------------------------------------------------------- #
# Which /25(s) the spec leaks, and the host(s) probed.
# --------------------------------------------------------------------------- #
def _leaked_specifics(topo: _Topo) -> list[str]:
    scope = topo.spec.leak_scope
    if scope == "low_half":
        return [topo.specific_low]
    if scope == "high_half":
        return [topo.specific_high]
    return [topo.specific_low, topo.specific_high]


def _pulled_hosts(topo: _Topo) -> list[str]:
    """Host IPs whose traffic the leak pulls toward the leaker (the affected flows)."""
    scope = topo.spec.leak_scope
    if scope == "low_half":
        return [topo.low_host]
    if scope == "high_half":
        return [topo.high_host]
    return [topo.low_host, topo.high_host]


def _control_hosts(topo: _Topo) -> list[str]:
    """Host IPs in the NON-leaked half(s) (negative controls)."""
    scope = topo.spec.leak_scope
    if scope == "low_half":
        return [topo.high_host]
    if scope == "high_half":
        return [topo.low_host]
    return []  # both halves leaked -> no in-prefix control host


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, matching baseline_leak_ms).
# --------------------------------------------------------------------------- #
def _frr_header(node: str) -> str:
    return (
        "frr version 10.6.1\n"
        "frr defaults traditional\n"
        f"hostname {node}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


def _victim_config(topo: _Topo) -> str:
    """Victim originates the protected /24 and HOSTS both halves' host IPs as real
    connected addresses (so it serves the whole /24 in the pre-state)."""
    p = topo.params
    lp = topo.loopback[topo.victim]
    # interfaces file
    body = [
        topo.victim, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {lp}/32", "",
        "auto eth1", "iface eth1 inet static", f"    address {topo.vt_victim}/30", "",
        # dum0 carries the .1 host (covers the low /25); dum1 carries the .129 host
        # (covers the high /25). Both are connected so the victim serves the entire
        # /24 in the baseline -> clean negative-control source for both halves.
        "auto dum0", "iface dum0 inet static", f"    address {topo.low_host}/25", "",
        "auto dum1", "iface dum1 inet static", f"    address {topo.high_host}/25", "",
        "# ports.conf --", "",
    ]
    iface_file = "\n".join(body) + "\n"
    stanzas = (
        f"interface lo\n ip address {lp}/32\n!\n"
        f"interface eth1\n ip address {topo.vt_victim}/30\n!\n"
        f"interface dum0\n ip address {topo.low_host}/25\n!\n"
        f"interface dum1\n ip address {topo.high_host}/25\n!\n"
    )
    bgp = (
        f"router bgp {p.asn_victim}\n"
        f" bgp router-id {lp}\n"
        f" neighbor {topo.vt_transit} remote-as {p.asn_transit}\n"
        " !\n address-family ipv4 unicast\n"
        f"  network {lp}/32\n"
        f"  network {topo.victim_prefix}\n"
        " exit-address-family\n!\nline vty\n!\n"
    )
    return iface_file + _frr_header(topo.victim) + stanzas + bgp


def _transit_config(topo: _Topo) -> str:
    """Transit observes both eBGP peers; originates only its loopback."""
    p = topo.params
    lp = topo.loopback[topo.transit]
    body = [
        topo.transit, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {lp}/32", "",
        "auto eth1", "iface eth1 inet static", f"    address {topo.vt_transit}/30", "",
        "auto eth2", "iface eth2 inet static", f"    address {topo.tl_transit}/30", "",
        "# ports.conf --", "",
    ]
    iface_file = "\n".join(body) + "\n"
    stanzas = (
        f"interface lo\n ip address {lp}/32\n!\n"
        f"interface eth1\n ip address {topo.vt_transit}/30\n!\n"
        f"interface eth2\n ip address {topo.tl_transit}/30\n!\n"
    )
    bgp = (
        f"router bgp {p.asn_transit}\n"
        f" bgp router-id {lp}\n"
        f" neighbor {topo.vt_victim} remote-as {p.asn_victim}\n"
        f" neighbor {topo.tl_leaker} remote-as {p.asn_leaker}\n"
        " !\n address-family ipv4 unicast\n"
        f"  network {lp}/32\n"
        " exit-address-family\n!\nline vty\n!\n"
    )
    return iface_file + _frr_header(topo.transit) + stanzas + bgp


def _leaker_config(topo: _Topo) -> str:
    """Leaker baseline: originates only its OWN /24 + loopback (no leak yet)."""
    p = topo.params
    lp = topo.loopback[topo.leaker]
    body = [
        topo.leaker, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {lp}/32", "",
        "auto eth1", "iface eth1 inet static", f"    address {topo.tl_leaker}/30", "",
        "auto dum0", "iface dum0 inet static", f"    address {topo.params.leaker_net}.1/24", "",
        "# ports.conf --", "",
    ]
    iface_file = "\n".join(body) + "\n"
    stanzas = (
        f"interface lo\n ip address {lp}/32\n!\n"
        f"interface eth1\n ip address {topo.tl_leaker}/30\n!\n"
        f"interface dum0\n ip address {topo.params.leaker_net}.1/24\n!\n"
    )
    bgp = (
        f"router bgp {p.asn_leaker}\n"
        f" bgp router-id {lp}\n"
        f" neighbor {topo.tl_transit} remote-as {p.asn_transit}\n"
        " !\n address-family ipv4 unicast\n"
        f"  network {lp}/32\n"
        f"  network {topo.leaker_prefix}\n"
        " exit-address-family\n!\nline vty\n!\n"
    )
    return iface_file + _frr_header(topo.leaker) + stanzas + bgp


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {
        topo.victim: _victim_config(topo),
        topo.transit: _transit_config(topo),
        topo.leaker: _leaker_config(topo),
    }


# --------------------------------------------------------------------------- #
# The leak (the change), rendered on the leaker per leak_kind + leak_scope.
# --------------------------------------------------------------------------- #
def _post_leaker_config(topo: _Topo) -> str:
    """Apply the leak to the leaker's baseline config.

    ms_blackhole: for each leaked /25, add a `network` + a backing DISCARD static
                  (`ip route <25> blackhole`). The leaker has NO real path -> LPM
                  pulls + drops at the leaker.
    ms_reroute:   for each leaked /25, add a `network` + a CONNECTED dummy
                  interface holding the victim's HOST address inside that /25 (so
                  the leaker ACCEPTS the pulled traffic -> delivered-but-rerouted).
    """
    before = _leaker_config(topo)
    leaked = _leaked_specifics(topo)
    kind = topo.spec.leak_kind

    # anchors in the baseline leaker config.
    iface_anchor = f"    address {topo.params.leaker_net}.1/24\n"  # in /etc/network/interfaces
    stanza_anchor = f"interface dum0\n ip address {topo.params.leaker_net}.1/24\n!\n"
    static_anchor = stanza_anchor  # statics go right after the dum0 stanza block
    network_anchor = f"  network {topo.leaker_prefix}\n"

    after = before
    if kind == "ms_blackhole":
        # discard statics (one per leaked /25), inserted after the dum0 stanza.
        statics = "".join(f"ip route {sp} blackhole\n" for sp in leaked)
        after = after.replace(static_anchor, static_anchor + statics, 1)
    else:  # ms_reroute: connected dummies holding the victim host IPs.
        # add interfaces-file stanzas + `interface` stanzas for each leaked half.
        host_for = {topo.specific_low: topo.low_host, topo.specific_high: topo.high_host}
        # /etc/network/interfaces dummies
        idx = 1
        new_iface_lines = ""
        new_stanzas = ""
        for sp in leaked:
            host = host_for[sp]
            new_iface_lines += (
                f"\nauto dum{idx}\niface dum{idx} inet static\n    address {host}/25\n"
            )
            new_stanzas += f"interface dum{idx}\n ip address {host}/25\n!\n"
            idx += 1
        after = after.replace(iface_anchor, iface_anchor + new_iface_lines, 1)
        after = after.replace(stanza_anchor, stanza_anchor + new_stanzas, 1)

    # the `network` statements (both kinds), inserted after the leaker's own /24.
    networks = "".join(f"  network {sp}\n" for sp in leaked)
    after = after.replace(network_anchor, network_anchor + networks, 1)
    return after


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
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: LeakSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    before = pre[topo.leaker]
    after = _post_leaker_config(topo)
    patch = _unified(before, after, topo.leaker)

    pulled = _pulled_hosts(topo)
    controls = _control_hosts(topo)

    # D2 watch set: all loopbacks + the victim /24 + the leaker /24 + the leaked
    # /25(s). The /25s are watched so a model that correctly reports them as ADDED
    # is not penalised, and so we can assert the legit /24 is NOT lost from any RIB.
    watched = (
        [f"{topo.loopback[n]}/32" for n in topo.nodes]
        + [topo.victim_prefix, topo.leaker_prefix]
        + _leaked_specifics(topo)
    )

    # Probes. transit -> each pulled host (the affected flow), transit -> each
    # control host (neg control: non-leaked half stays at the victim), transit ->
    # leaker's own host (neg control), and victim -> each pulled host (neg control:
    # the victim serves it connected in both snapshots).
    leaker_host = f"{params.leaker_net}.1/32"
    reach: list[tuple[str, str]] = []
    fwd: list[tuple[str, str]] = []
    waypoints: list[tuple[str, str, str]] = []
    intent_invariants: list[IntentInvariant] = []

    for h in pulled:
        reach.append((topo.transit, f"{h}/32"))
        fwd.append((topo.transit, f"{h}/32"))
        # ms_reroute: the path dimension carries the blast. Declare the victim as
        # the required waypoint for victim-host-bound traffic (oracle-side only).
        if spec.leak_kind == "ms_reroute":
            waypoints.append((topo.transit, f"{h}/32", topo.victim))
            intent_invariants.append(IntentInvariant(
                kind="waypoint", src=topo.transit, dst=f"{h}/32", waypoint=topo.victim,
                note=(
                    "Victim-host traffic MUST transit the victim AS (the legitimate "
                    "origin). The more-specific leak pulls it to the leaker by LPM; "
                    "the leaker delivers it (reachability survives) but the victim is "
                    "bypassed -> a path/intent violation D1-D3 cannot catch."
                ),
            ))
    for h in controls:
        reach.append((topo.transit, f"{h}/32"))   # neg control: non-leaked half
        fwd.append((topo.transit, f"{h}/32"))
    # neg controls present in every combo:
    reach.append((topo.transit, leaker_host))
    fwd.append((topo.transit, leaker_host))
    for h in pulled:
        reach.append((topo.victim, f"{h}/32"))     # victim serves it connected

    name = f"gen_leak_{spec.dims_label()}_s{seed}"

    # Prose (CONFIG EDIT + INTENT ONLY — never the outcome; prompt-hygiene gate).
    halves = {
        "low_half": "the lower /25", "high_half": "the upper /25",
        "both_halves": "both /25 halves",
    }[spec.leak_scope]
    if spec.leak_kind == "ms_blackhole":
        backing = "each backed by a discard (null) static route"
    else:
        backing = (
            "each backed by a directly-connected interface in that range"
        )
    description = (
        f"On the leaker ({topo.leaker}, AS{params.asn_leaker}), originate "
        f"{halves} of the {topo.victim_prefix} block ("
        + ", ".join(f"network {sp}" for sp in _leaked_specifics(topo))
        + f"), {backing}. See the diff and the per-node configs."
    )
    intents_text = (
        f"The leaker (AS{params.asn_leaker}) should only advertise prefixes it "
        f"legitimately serves ({topo.leaker_prefix}). All traffic toward the "
        f"victim's customer space {topo.victim_prefix} MUST continue to be served "
        f"by the victim (AS{params.asn_victim})."
    )

    scn = Scenario(
        name=name,
        nodes=list(topo.nodes),
        pre_configs=pre,
        change_target=topo.leaker,
        patch=patch,
        description=description,
        intents_text=intents_text,
        watched_prefixes=watched,
        reachability_flows=reach,
        forwarding_flows=fwd,
        waypoint_intents=waypoints,
        intent_invariants=intent_invariants,
        is_trap=True,
        provenance="templated",
    )
    return scn


# --------------------------------------------------------------------------- #
# Public API (mirrors generator_ipc).
# --------------------------------------------------------------------------- #
def generate_leak(seed: int, spec: Optional[LeakSpec] = None) -> Scenario:
    """Emit ONE Class-2 instance.

    With ``spec=None`` the axis tuple is chosen deterministically from ``seed`` (so
    a bare ``generate_leak(s)`` is reproducible and covers the space as ``s``
    varies). Passing an explicit ``spec`` pins the structure and uses ``seed`` only
    for the randomized addressing — how the suite enumerates every combo with
    distinct numbering.
    """
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def generate_leak_suite(n: int, *, base_seed: int = 0) -> list[Scenario]:
    """Emit ``n`` DISTINCT Class-2 instances with unique ids.

    Walk the valid axis space in order, assigning each spec a distinct seed
    (``base_seed + position``) so the structure AND the randomized numbering both
    vary. If ``n`` exceeds the axis count we wrap with a fresh seed, giving the SAME
    structure a NEW randomized instance (still novel, still unique-id; the seed is
    in the name so ids never collide).
    """
    specs = enumerate_specs()
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        seed = base_seed + i
        out.append(_scenario_from_spec(spec, seed))
    return out


def enumerable_count() -> int:
    """Number of distinct axis combinations (each x infinite randomized seeds)."""
    return len(enumerate_specs())
