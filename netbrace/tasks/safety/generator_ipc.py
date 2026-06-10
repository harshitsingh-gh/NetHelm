"""Class-1 generator — internal routing-policy "implicit-deny" silent withdrawal.

This is the FIRST real parameterized generator (Plan-C scale unblocker). It turns
the verified Class-1 MECHANISM (an iBGP route-map "cleanup" that silently withdraws
a customer prefix while every BGP session stays ESTABLISHED — the documented LLM
trap) into N DISTINCT, oracle-gradeable instances over determinism-SAFE axes, with
per-seed randomized ASN / addressing / node-names / customer-prefix as the
CONTAMINATION CONTROL (the mechanism is public; each emitted instance is novel).

Relationship to the hand-authored family (scenario_ipc / ipc_fanout / ipc_static /
ipc_aggregate): those are the GROUNDED, incident-anchored templates this generator
is parameterized FROM. Generated instances set ``provenance="templated"`` (the
PRIMARY decontaminated split); the hand-authored ones keep ``"handauthored"`` (the
GROUNDED split). The mechanism is identical and verified; the generator's value is
DIVERSITY of blast STRUCTURE + difficulty + novel numbering, not new mechanisms.

Axes (each a genuinely distinct blast structure or a legit difficulty variant, NOT
a clone — see ``AXES`` / ``enumerate_specs``):

  * topology shape ``k`` ∈ {2,3,4}   — RR + k leaf clients + 1 origin. Different
    fan-out → different negative-control set; with ``filtered="all"`` it also drives
    D2/D3 cardinality.
  * filtered set ``one`` | ``all``    — filter one client vs the whole client
    peer-group → D2/D3 cardinality 1 vs k (a different affected-node SET).
  * direction ``out`` | ``in``        — the SAME blast, different CAUSE LOCUS: the
    filter is outbound on the RR (advertise-suppression) vs inbound on the affected
    client(s) (accept-suppression). Forces the model to read a different device.
  * prefix class ``plain`` | ``static`` | ``aggregate``:
      - ``plain``    — customer /24, no static backup → coupled D2 + D3 (clean
        NO_ROUTE), the flagship structure.
      - ``static``   — affected client(s) have a STATIC backup to the /24 → the
        BGP route is withdrawn (D9 fires) but the FIB + reachability survive
        (D2 = ∅, D3 = ∅): a CONTROL-PLANE-only event. D9 opted in.
      - ``aggregate``— origin pins a /24 aggregate + two /25 more-specifics; the
        filter permits the /24 but drops the /25s → D2 on the /25s, D3 = ∅ (the /24
        still covers it), and an oracle-side ``te_pin`` invariant → D10 fires.
  * match construction (difficulty) ``implicit`` | ``explicit_deny`` | ``wrong_le``
    — the SAME ground truth, different config-reading difficulty:
      - ``implicit``     — permit the keep-set, rely on the route-map implicit
        deny-all (the classic "forgot the final permit any").
      - ``explicit_deny``— permit the keep-set, then an EXPLICIT deny of the
        customer prefix, then permit any: the deny is visible but easy to miss
        because a trailing permit-any "looks safe".
      - ``wrong_le``     — a single ``permit 10.0.0.0/8 le 31`` style bound whose
        ``le`` is too short to cover the customer prefix's length (an off-by-one
        boundary the reader must compute). Only valid for ``plain``/``static``
        (it depends on a single mis-bounded keep clause).
  Not every (prefix, match) pair is meaningful — ``aggregate`` always uses an
  exact-/24 permit (its whole point), so it is paired only with ``implicit`` and
  ``explicit_deny``; ``wrong_le`` only with ``plain``/``static``. See ``_valid``.

Randomization (per seed, deterministic — same seed ⇒ byte-identical instance):
  * ASN drawn from the private 4-byte range (avoids collision with the
    hand-authored 65000 family).
  * loopback /32 block + per-link /30s drawn from disjoint RFC-1918-ish pools.
  * node base name (the SAME node still maps to its loopback/router-id; only the
    *string* changes, so a contamination-matched instance is unrecognisable).
  * customer prefix drawn from the documentation/TEST-NET / RFC-1918 customer pools.

Determinism contract (oracle_determinism_spec_v1.md, Class 1 = STATIC-DET):
filtering is prefix-list + route-map ONLY (no FRR access-list); router-ids are
PINNED to the (randomized but fixed-per-seed) loopback; loopbacks always have a
static backup so iBGP sessions stay up; the customer prefix has NO static backup
(except the ``static`` variant, which is the whole point of that variant). Each
emitted Scenario round-trips and is gradeable by ExtendedOracle.compute unchanged.
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
K_VALUES = (2, 3, 4)
FILTERED_VALUES = ("one", "all")
DIRECTION_VALUES = ("out", "in")
PREFIX_VALUES = ("plain", "static", "aggregate")
MATCH_VALUES = ("implicit", "explicit_deny", "wrong_le")

AXES = {
    "k": K_VALUES,
    "filtered": FILTERED_VALUES,
    "direction": DIRECTION_VALUES,
    "prefix": PREFIX_VALUES,
    "match": MATCH_VALUES,
}


@dataclass(frozen=True)
class IpcSpec:
    """A point in the Class-1 generator space (the axis tuple, pre-randomization)."""

    k: int
    filtered: str
    direction: str
    prefix: str
    match: str

    def dims_label(self) -> str:
        return f"k{self.k}-{self.filtered}-{self.direction}-{self.prefix}-{self.match}"


def _valid(spec: IpcSpec) -> bool:
    """Reject axis combinations that are not mechanistically meaningful.

    * ``wrong_le`` depends on a single mis-bounded keep clause that fails to cover
      the customer /24 — it is only meaningful for ``plain``/``static`` (the
      ``aggregate`` variant deliberately permits the exact /24, so a ``le`` bound is
      not the mechanism there).
    * ``aggregate`` only pairs with ``implicit`` / ``explicit_deny`` (above).
    """
    if spec.match == "wrong_le" and spec.prefix == "aggregate":
        return False
    return True


def enumerate_specs() -> list[IpcSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[IpcSpec] = []
    for k in K_VALUES:
        for filtered in FILTERED_VALUES:
            for direction in DIRECTION_VALUES:
                for prefix in PREFIX_VALUES:
                    for match in MATCH_VALUES:
                        spec = IpcSpec(k, filtered, direction, prefix, match)
                        if _valid(spec):
                            out.append(spec)
    return out


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996): 4200000000-4294967294. We keep clear of the
# hand-authored 65000 family so a generated instance never collides with it.
_ASN_LO, _ASN_HI = 4_200_000_000, 4_200_099_999

# Disjoint loopback /24 pools (each instance takes ONE /24 and carves /32s from it).
_LOOPBACK_POOLS = ["10.{a}.{b}.0", "172.{a2}.{b}.0"]  # rendered below

# Customer-prefix pools (documentation / TEST-NET / RFC-1918 customer space). Each
# instance draws ONE /24 from here for the withdrawn customer prefix.
_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

# Node base-name pools (string only; topology role is unchanged).
_NAME_POOLS = ["r", "rtr", "pe", "node", "leaf", "edge"]


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    asn: int
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    name_base: str           # e.g. "pe"


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)
    asn = rng.randint(_ASN_LO, _ASN_HI)

    # loopback /24: 10.<1-250>.<0-250>.0  (then /32s 10.x.y.N)
    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"

    # link /30 supernet: 192.<0-250>.<0-250>.0  (carve /30s for each link)
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    # customer /24 base (render any {c} placeholder)
    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    name_base = rng.choice(_NAME_POOLS)
    return _Params(asn=asn, loop_block=loop_block, link_block=link_block,
                   customer_net=customer_net, name_base=name_base)


# --------------------------------------------------------------------------- #
# Topology builder: an RR (index 1) + k leaf clients + 1 origin, deterministic
# addressing derived from the randomized blocks.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    """A concrete, addressed RR-fanout topology for one instance."""

    params: _Params
    spec: IpcSpec
    nodes: list[str]                       # ordered: rr, clients..., origin
    rr: str
    clients: list[str]                     # the k leaf clients
    origin: str
    loopback: dict[str, str]               # node -> "x.y.z.N"
    rid_index: dict[str, int]              # node -> the integer N in the loopback
    near_ip: dict[str, str]                # node -> its IP on its rr-facing /30
    rr_far_ip: dict[str, str]              # node -> the rr-side IP toward that node
    customer_prefix: str                   # "<net>/24"
    customer_ip: str                       # an address inside it
    aggregate_prefix: str                  # "<net>/24" (== customer for aggregate)
    specific_low: str                      # "<net>/25"
    specific_high: str                     # "<net>.128/25"


def _name(base: str, idx: int) -> str:
    return f"{base}{idx}"


def _build_topo(spec: IpcSpec, params: _Params) -> _Topo:
    base = params.name_base
    n_total = spec.k + 2  # rr + k clients + origin
    indices = list(range(1, n_total + 1))
    node_names = [_name(base, i) for i in indices]
    rr = node_names[0]
    clients = node_names[1 : 1 + spec.k]
    origin = node_names[-1]

    loopback = {n: f"{params.loop_block}.{i}" for n, i in zip(node_names, indices)}
    rid_index = {n: i for n, i in zip(node_names, indices)}

    # Each non-rr node gets a /30 link to the rr. Link i uses
    # 192.b.c.(4*i)/30: rr = .(4*i+1), node = .(4*i+2).
    b, c0, c1 = params.link_block
    near_ip: dict[str, str] = {}
    rr_far_ip: dict[str, str] = {}
    for li, node in enumerate(node_names[1:]):  # clients + origin, in order
        base4 = 4 * li
        rr_far_ip[node] = f"{b}.{c0}.{c1}.{base4 + 1}"
        near_ip[node] = f"{b}.{c0}.{c1}.{base4 + 2}"

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.10"
    aggregate_prefix = customer_prefix
    specific_low = f"{params.customer_net}.0/25"
    specific_high = f"{params.customer_net}.128/25"

    return _Topo(
        params=params, spec=spec, nodes=node_names, rr=rr, clients=clients,
        origin=origin, loopback=loopback, rid_index=rid_index, near_ip=near_ip,
        rr_far_ip=rr_far_ip, customer_prefix=customer_prefix, customer_ip=customer_ip,
        aggregate_prefix=aggregate_prefix, specific_low=specific_low,
        specific_high=specific_high,
    )


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, the verified baseline format).
# --------------------------------------------------------------------------- #
_LINK_MASK = "/30"


def _static_loopback_routes(topo: _Topo, node: str) -> list[str]:
    """Static routes so loopbacks are BGP-INDEPENDENT (sessions stay up).

    A client/origin reaches the RR's loopback directly via its /30; it reaches
    every OTHER loopback via the RR's near-side IP (the RR is sole transit). The RR
    reaches each loopback via that node's near-side IP.
    """
    lp = topo.loopback
    routes: list[str] = []
    if node == topo.rr:
        for other in topo.nodes:
            if other == topo.rr:
                continue
            routes.append(f"ip route {lp[other]}/32 {topo.near_ip[other]}")
    else:
        for other in topo.nodes:
            if other == node:
                continue
            if other == topo.rr:
                nh = topo.rr_far_ip[node]
            else:
                # via the RR (sole transit): use the rr-side IP on THIS node's link.
                nh = topo.rr_far_ip[node]
            routes.append(f"ip route {lp[other]}/32 {nh}")
    return routes


def _iface_block(node: str, topo: _Topo, extra_ifaces: list[tuple[str, str]]) -> str:
    """The /etc/network/interfaces + `interface` stanzas for a node."""
    lp = topo.loopback[node]
    lines = [
        node, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {lp}/32", "",
    ]
    # the rr-facing (or rr's per-client) physical links
    if node == topo.rr:
        for li, other in enumerate(topo.nodes[1:], start=1):
            ip = topo.rr_far_ip[other]
            lines += [f"auto eth{li}", f"iface eth{li} inet static",
                      f"    address {ip}{_LINK_MASK}", ""]
    else:
        ip = topo.near_ip[node]
        lines += ["auto eth1", "iface eth1 inet static",
                  f"    address {ip}{_LINK_MASK}", ""]
    # extra interfaces (e.g. the origin's customer-facing dummy)
    di = 0
    for addr, _mask in extra_ifaces:
        lines += [f"auto dum{di}", f"iface dum{di} inet static",
                  f"    address {addr}", ""]
        di += 1
    lines.append("# ports.conf --")
    lines.append("")
    return "\n".join(lines) + "\n"


def _frr_header(node: str) -> str:
    return (
        "frr version 10.6.1\n"
        "frr defaults traditional\n"
        f"hostname {node}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


def _interface_stanzas(node: str, topo: _Topo, extra: list[tuple[str, str]]) -> str:
    lp = topo.loopback[node]
    out = [f"interface lo\n ip address {lp}/32\n!"]
    if node == topo.rr:
        for li, other in enumerate(topo.nodes[1:], start=1):
            out.append(f"interface eth{li}\n ip address {topo.rr_far_ip[other]}{_LINK_MASK}\n!")
    else:
        out.append(f"interface eth1\n ip address {topo.near_ip[node]}{_LINK_MASK}\n!")
    di = 0
    for addr, _mask in extra:
        out.append(f"interface dum{di}\n ip address {addr}\n!")
        di += 1
    return "\n".join(out) + "\n"


def _rr_config(topo: _Topo) -> str:
    p = topo.params
    body = [_iface_block(topo.rr, topo, []), _frr_header(topo.rr),
            _interface_stanzas(topo.rr, topo, [])]
    body += [r + "\n" for r in _static_loopback_routes(topo, topo.rr)]
    body.append("!\n")
    body.append(f"router bgp {p.asn}\n")
    body.append(f" bgp router-id {topo.loopback[topo.rr]}\n")
    for other in topo.nodes[1:]:
        body.append(f" neighbor {topo.loopback[other]} remote-as {p.asn}\n")
        body.append(f" neighbor {topo.loopback[other]} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    for other in topo.nodes[1:]:
        body.append(f"  neighbor {topo.loopback[other]} route-reflector-client\n")
        body.append(f"  neighbor {topo.loopback[other]} next-hop-self\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _client_config(topo: _Topo, node: str, *, static_customer: bool) -> str:
    p = topo.params
    body = [_iface_block(node, topo, []), _frr_header(node),
            _interface_stanzas(node, topo, [])]
    body += [r + "\n" for r in _static_loopback_routes(topo, node)]
    if static_customer:
        # has-static sibling: a static backup to the customer /24 via the RR.
        body.append(f"ip route {topo.customer_prefix} {topo.rr_far_ip[node]}\n")
    body.append("!\n")
    body.append(f"router bgp {p.asn}\n")
    body.append(f" bgp router-id {topo.loopback[node]}\n")
    body.append(f" neighbor {topo.loopback[topo.rr]} remote-as {p.asn}\n")
    body.append(f" neighbor {topo.loopback[topo.rr]} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  neighbor {topo.loopback[topo.rr]} next-hop-self\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _origin_config(topo: _Topo) -> str:
    p = topo.params
    if topo.spec.prefix == "aggregate":
        extra = [(f"{topo.params.customer_net}.1/25", "/25"),
                 (f"{topo.params.customer_net}.129/25", "/25")]
        networks = [topo.aggregate_prefix, topo.specific_low, topo.specific_high]
        discard = [f"ip route {topo.aggregate_prefix} Null0"]
    else:
        extra = [(f"{topo.customer_ip}/24", "/24")]
        networks = [topo.customer_prefix]
        discard = []
    body = [_iface_block(topo.origin, topo, extra), _frr_header(topo.origin),
            _interface_stanzas(topo.origin, topo, extra)]
    body += [r + "\n" for r in _static_loopback_routes(topo, topo.origin)]
    body += [d + "\n" for d in discard]
    body.append("!\n")
    body.append(f"router bgp {p.asn}\n")
    body.append(f" bgp router-id {topo.loopback[topo.origin]}\n")
    body.append(f" neighbor {topo.loopback[topo.rr]} remote-as {p.asn}\n")
    body.append(f" neighbor {topo.loopback[topo.rr]} update-source lo\n")
    body.append(" !\n address-family ipv4 unicast\n")
    for net in networks:
        body.append(f"  network {net}\n")
    body.append(f"  neighbor {topo.loopback[topo.rr]} next-hop-self\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    static_customer = topo.spec.prefix == "static"
    cfgs = {topo.rr: _rr_config(topo)}
    for c in topo.clients:
        cfgs[c] = _client_config(topo, c, static_customer=static_customer)
    cfgs[topo.origin] = _origin_config(topo)
    return cfgs


# --------------------------------------------------------------------------- #
# The CLEANUP filter (the change). Rendered per direction + match construction.
# --------------------------------------------------------------------------- #
def _keep_prefix_lines(topo: _Topo) -> list[str]:
    """Permit clauses for the legitimate keep-set (loopbacks + link nets).

    The loopback /24 and the link /24 are permitted with a wide ``le`` so the /32
    loopbacks and /30 link nets survive. The customer prefix is NEVER in this set —
    that omission (or an explicit deny / a too-short ``le``) is the trap.
    """
    p = topo.params
    loop24 = f"{p.loop_block}.0/24"
    link24 = f"{p.link_block[0]}.{p.link_block[1]}.{p.link_block[2]}.0/24"
    return [
        f"ip prefix-list CLEANUP seq 5 permit {loop24} le 32",
        f"ip prefix-list CLEANUP seq 10 permit {link24} le 32",
    ]


def _filter_block(topo: _Topo, rmap: str) -> list[str]:
    """The prefix-list + route-map lines, per the match-construction axis."""
    spec = topo.spec
    lines = list(_keep_prefix_lines(topo))
    if spec.match == "wrong_le":
        # Replace the keep-set with a single aggregate-permit whose le bound is too
        # short to cover the customer /24. We use the LOOPBACK /8 permit with le 24,
        # plus the customer aggregate as a /16-or-shorter that does NOT match a /24
        # via the loop list. Concretely: permit the customer SUPERNET /16 le 23 —
        # the /24 needs le>=24, so it is dropped by the off-by-one boundary.
        p = topo.params
        loop24 = f"{p.loop_block}.0/24"
        link24 = f"{p.link_block[0]}.{p.link_block[1]}.{p.link_block[2]}.0/24"
        cust16 = f"{p.customer_net.rsplit('.', 1)[0]}.0.0/16"
        lines = [
            f"ip prefix-list CLEANUP seq 5 permit {loop24} le 32",
            f"ip prefix-list CLEANUP seq 10 permit {link24} le 32",
            # le 23 stops one bit short of the /24 customer prefix => it is dropped.
            f"ip prefix-list CLEANUP seq 15 permit {cust16} le 23",
        ]
    if spec.prefix == "aggregate":
        # Permit the /24 aggregate EXACTLY (no le) so the /25 more-specifics fall to
        # the implicit deny; insert it ahead of the wide keep clauses.
        lines = [f"ip prefix-list CLEANUP seq 1 permit {topo.aggregate_prefix}"] + lines

    out = list(lines)
    if spec.match == "explicit_deny":
        # Deny the route(s) the change is meant to suppress, then a trailing
        # permit-any that "looks safe" (the trap: the deny is what bites).
        #   * aggregate: deny the two /25 more-specifics (the /24 must survive).
        #   * plain/static: deny the customer /24.
        if spec.prefix == "aggregate":
            out.append(f"ip prefix-list CLEANUP seq 80 deny {topo.specific_low}")
            out.append(f"ip prefix-list CLEANUP seq 85 deny {topo.specific_high}")
        else:
            out.append(f"ip prefix-list CLEANUP seq 90 deny {topo.customer_prefix}")
        out.append("ip prefix-list CLEANUP seq 100 permit 0.0.0.0/0 le 32")
    out.append(f"route-map {rmap} permit 10")
    out.append(" match ip address prefix-list CLEANUP")
    out.append("!")
    return out


def _apply_filter(topo: _Topo) -> tuple[dict[str, str], list[str]]:
    """Return (per-node diffs, changed-nodes) applying the CLEANUP filter.

    direction="out": filter outbound on the RR toward the filtered client(s).
    direction="in":  filter inbound on each filtered client toward the RR.
    """
    spec = topo.spec
    targets = topo.clients if spec.filtered == "all" else [topo.clients[0]]
    pre = _baseline_configs(topo)
    diffs: dict[str, str] = {}

    if spec.direction == "out":
        # one route-map on the RR, attached toward each target client.
        rmap = "TO_CLIENTS_OUT"
        before = pre[topo.rr]
        block = "\n".join(_filter_block(topo, rmap)) + "\n"
        # anchor: after the static-route block, before `router bgp`.
        anchor = f"router bgp {topo.params.asn}\n"
        after = before.replace(anchor, block + anchor, 1)
        # attach the route-map outbound to each target inside the address-family.
        af_anchor = " exit-address-family\n"
        attach = "".join(
            f"  neighbor {topo.loopback[t]} route-map {rmap} out\n" for t in targets
        )
        after = after.replace(af_anchor, attach + af_anchor, 1)
        diffs[topo.rr] = _unified(before, after, topo.rr)
        return diffs, [topo.rr]

    # direction == "in": filter inbound on each target client toward the RR.
    rmap = "FROM_RR_IN"
    changed = []
    for t in targets:
        before = pre[t]
        block = "\n".join(_filter_block(topo, rmap)) + "\n"
        anchor = f"router bgp {topo.params.asn}\n"
        after = before.replace(anchor, block + anchor, 1)
        af_anchor = " exit-address-family\n"
        attach = f"  neighbor {topo.loopback[topo.rr]} route-map {rmap} in\n"
        after = after.replace(af_anchor, attach + af_anchor, 1)
        diffs[t] = _unified(before, after, t)
        changed.append(t)
    return diffs, changed


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
def _scenario_from_spec(spec: IpcSpec, seed: int) -> Scenario:
    params = _draw_params(seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    diffs, changed = _apply_filter(topo)

    targets = topo.clients if spec.filtered == "all" else [topo.clients[0]]
    unaffected_clients = [c for c in topo.clients if c not in targets]

    # Probes ---------------------------------------------------------------- #
    if spec.prefix == "aggregate":
        # watch aggregate + both /25s + all loopbacks (negative controls).
        watched = (
            [f"{topo.loopback[n]}/32" for n in topo.nodes]
            + [topo.aggregate_prefix, topo.specific_low, topo.specific_high]
        )
        # probe each affected client to an IP inside each /25, plus a control client.
        reach = []
        for t in targets:
            reach.append((t, f"{params.customer_net}.10"))   # inside low /25
            reach.append((t, f"{params.customer_net}.200"))  # inside high /25
        reach += [(topo.rr, f"{params.customer_net}.10"),
                  (topo.origin, f"{params.customer_net}.10")]
        intent_invariants = []
        for t in targets:
            intent_invariants += [
                IntentInvariant(kind="te_pin", src=t, dst=topo.specific_low,
                                note="origin pins the low /25 for inbound TE; the "
                                     "CLEANUP filter withdraws it, collapsing it onto "
                                     "the /24 (reachable but de-pinned)."),
                IntentInvariant(kind="te_pin", src=t, dst=topo.specific_high,
                                note="origin pins the high /25 for inbound TE; same "
                                     "collapse onto the /24 aggregate."),
            ]
        bgp_watch: list[str] = []
    else:
        watched = (
            [f"{topo.loopback[n]}/32" for n in topo.nodes] + [topo.customer_prefix]
        )
        reach = [(t, topo.customer_prefix) for t in targets]
        reach += [(topo.rr, topo.customer_prefix), (topo.origin, topo.customer_prefix)]
        reach += [(c, topo.customer_prefix) for c in unaffected_clients]
        intent_invariants = []
        # the has-static sibling enables D9 (the control-plane discriminator).
        bgp_watch = [topo.customer_prefix] if spec.prefix == "static" else []

    # combined human-readable diff (concat of all per-node diffs, sorted by node).
    combined = "".join(diffs[n] for n in sorted(diffs))
    change_target = changed[0]

    # Prose (CONFIG EDIT + INTENT ONLY — never the outcome; prompt-hygiene gate).
    where = ("the route reflector's iBGP sessions toward the access router(s)"
             if spec.direction == "out"
             else "the access router's inbound iBGP session from the route reflector")
    kept = "the backbone loopbacks and the link nets"
    if spec.prefix == "aggregate":
        kept = "the covering customer /24 aggregate, the loopbacks, and the link nets"
    description = (
        f"Attach a 'cleanup' prefix-list (CLEANUP) + route-map to {where} to reduce "
        f"advertisement noise. The filter permits {kept}. See the per-node configs "
        f"and the diff."
    )
    intents_text = (
        "Reduce iBGP advertisement noise toward the access router(s). All customer "
        "and service reachability MUST be preserved."
    )

    name = f"gen_ipc_{spec.dims_label()}_s{seed}"
    scn = Scenario(
        name=name,
        nodes=list(topo.nodes),
        pre_configs=pre,
        change_target=change_target,
        patch=combined,
        patches=diffs if len(diffs) > 1 else {},
        description=description,
        intents_text=intents_text,
        watched_prefixes=watched,
        reachability_flows=reach,
        bgp_watch_prefixes=bgp_watch,
        intent_invariants=intent_invariants,
        is_trap=True,
        provenance="templated",
    )
    return scn


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #
def generate_ipc_withdrawal(seed: int, spec: Optional[IpcSpec] = None) -> Scenario:
    """Emit ONE Class-1 instance.

    With ``spec=None`` the axis tuple is chosen deterministically from ``seed``
    (so a bare ``generate_ipc_withdrawal(s)`` is reproducible and covers the space
    as ``s`` varies). Passing an explicit ``spec`` pins the structure and uses
    ``seed`` only for the randomized addressing — this is how the suite enumerates
    every axis combination with distinct numbering.
    """
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def generate_ipc_suite(n: int, *, base_seed: int = 0) -> list[Scenario]:
    """Emit ``n`` DISTINCT Class-1 instances with unique ids.

    Coverage strategy: walk the valid axis space in order and assign each spec a
    distinct seed (``base_seed + position``) so the structure AND the randomized
    numbering both vary. If ``n`` exceeds the axis count we wrap with a fresh seed
    offset, giving the SAME structure a NEW randomized instance (still novel, still
    unique-id). Ids are guaranteed unique (seed is in the name).
    """
    specs = enumerate_specs()
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        seed = base_seed + i
        out.append(_scenario_from_spec(spec, seed))
    return out


def enumerable_count() -> int:
    """Number of distinct axis combinations (each ×∞ randomized seeds)."""
    return len(enumerate_specs())
