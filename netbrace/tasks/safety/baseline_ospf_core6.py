"""The `ospf_core6` baseline: a 6-node single-AS OSPF-underlay / iBGP-overlay core.

VERDICT (2026-06-10, netdevops-engineer): **CLEAN KILL — NOT a registered scenario.**
This baseline is a verified, parse-clean, fully-idiomatic OSPF-underlay topology
(zero static routes; every iBGP next-hop resolves recursively via the OSPF RIB — the
crutch-killer property PROVEN on live Batfish). But the intended SCENARIO — an
OSPF-underlay change that makes the customer prefix's iBGP next-hop unresolvable on a
SUBSET of nodes while every iBGP session stays ESTABLISHED (D1=∅ with D2/D7 firing) —
is **STRUCTURALLY IMPOSSIBLE on this exact 6-node 2-plane topology**, confirmed by an
exhaustive sweep of all 42 single/double OSPF link cuts across both next-hop baselines
(plain `next-hop-self` and the idiomatic route-map `set ip next-hop`): **0 clean
traps** — every cut either merely REROUTES (D1=∅ but the prefix survives everywhere,
8 cases) or strands a node and drops an iBGP session (D1 fires, 34 cases).

Root cause (the honest negative result, worth a paper case-study figure): the customer
prefix's iBGP next-hop is reachable through exactly the same underlay paths that carry
the victim's iBGP sessions, so on a healthy redundant 2-plane RR core the two cannot
be decoupled:
  * If next-hop = the ORIGIN loopback (10.0.0.6, plain `next-hop-self` — which Batfish
    keeps because plain next-hop-self is a documented NO-OP for RR-reflected routes,
    matching NVIDIA Cumulus / Cisco semantics), 10.0.0.6 is single-homed behind agg2;
    any cut removing a node's reachability to it also strands that node (or agg2/edge2)
    from an RR -> an iBGP session drops.
  * If next-hop = an RR loopback (idiomatic route-map `set ip next-hop <RR-lo>` toward
    clients, which Batfish DOES honor), the SAME RR-loopback reachability gates both the
    iBGP session and the recursive resolution; lose it and the session drops, keep it
    and BGP best-path fails over to the other plane's RR copy -> reroute, no loss.
The very redundancy that makes this a *good* 2-plane core is what defeats the intended
failure. A clean kill is a valid, valuable outcome (per the build gate): NOT hacked
around with a static route or an IS-IS substitute.

v1.5 fix path (makes the mechanism fire): DUAL-HOME the customer edge so the prefix's
next-hop has 2-plane diversity DECOUPLED from a victim's iBGP, OR add a node whose ONLY
path to the prefix's origin is single-homed while its iBGP to both RRs survives on a
disjoint plane. (Verified: simply dual-homing edge2 keeps all 18 sessions up but still
only reroutes; the v1.5 design needs an engineered SPOF on the customer-attach plane
that the victim's iBGP does not traverse.) This baseline is the foundation for that fix.

This file is KEPT as the documented case-study artifact + v1.5 foundation. It is NOT in
REGISTRY and is imported by nothing (no scenario_/test_ companion, no REGISTRY entry) —
registering a scenario that cannot fire its intended dimensions would be the hack the
build gate forbids.

----------------------------------------------------------------------------------------

ORIGINAL DESIGN INTENT (retained for the v1.5 fix):

This is the FIRST IGP-underlay scenario in NetHELM and its purpose is to KILL the
non-idiomatic static-next-hop crutch every prior scenario uses. Every earlier iBGP
scenario gives the receiver STATIC routes to the egress link /30s so the
iBGP-advertised next-hop resolves (the documented Batfish-FRR next-hop-self gap,
see docs/oracle_determinism_spec_v1.md). That crutch is fine for the prefix-filter
classes but it MASKS the entire family of recursive-next-hop / IGP-underlay
failures — the moment you add a static route, an OSPF cut no longer blackholes,
because the static keeps the FIB populated. So this scenario contains **ABSOLUTELY
NO static routes anywhere**: every loopback /32 is advertised into OSPF area 0, and
every iBGP loopback next-hop is resolved RECURSIVELY via the OSPF RIB (RFC 4271
§9.1.2). A single `ip route` would defeat the whole point.

Topology — a redundant 2-plane core (real path diversity, NOT a line)::

      edge1 ---- agg1 ---- rr1
                  |  \\      |
                  |   \\     |   (rr1-rr2 is the cross-link between RR planes)
      edge2 ---- agg2 ---- rr2
                      \\____/
                  (agg1-agg2 cross-link)

  6 point-to-point /30 links, ALL in OSPF area 0:
    L0 edge1-agg1   L1 edge2-agg2   L2 agg1-rr1   L3 agg2-rr2
    L4 rr1-rr2      L5 agg1-agg2

  * rr1, rr2 are iBGP route-reflectors (also OSPF speakers).
  * agg1, agg2 are aggregation/transit (OSPF + iBGP RR clients).
  * edge1, edge2 are edges (OSPF + iBGP RR clients). edge2 originates the customer
    prefix 203.0.113.0/24 (BGP-only reachability, no static, no `network` backup).

Why the 2-plane core matters: a naive single OSPF cost-out just REROUTES (the other
plane carries the loopback), which would be a DEAD scenario. The scenario change
(scenario_ospf_core6.py) is engineered to remove a node's ONLY usable OSPF
resolution path to the next-hop that resolves the customer prefix, so the prefix
becomes unresolvable / blackholes THERE while every iBGP session stays ESTABLISHED.

iBGP overlay (single AS 65000):
  * rr1, rr2 are RRs: each peers the other RR (plain iBGP) and reflects to all four
    clients (agg1, agg2, edge1, edge2) with `route-reflector-client` + `next-hop-self`.
    `update-source lo` on every iBGP session (peer over loopbacks).
  * agg1/agg2/edge1/edge2 are clients: each peers BOTH RRs (rr1 + rr2) over loopbacks
    with `update-source lo`. No client-client peering (the RRs are the transit).
  * next-hop-self on the RRs means a client learns the customer prefix with the RR's
    LOOPBACK as the BGP next-hop; that loopback is resolved via the OSPF RIB — the
    idiomatic recursive resolution this scenario exists to exercise.

Deterministic addressing (docs/authoring_topologies_and_scenarios.md §1):
  loopbacks 10.0.0.{1..6}/32 == OSPF router-id == bgp router-id, one per node:
    rr1=10.0.0.1  rr2=10.0.0.2  agg1=10.0.0.3  agg2=10.0.0.4
    edge1=10.0.0.5  edge2=10.0.0.6
  p2p /30 links from 192.0.2.0/24 (lower-IP end listed first):
    L0 edge1-agg1  192.0.2.0/30   (edge1=.1,  agg1=.2)
    L1 edge2-agg2  192.0.2.4/30   (edge2=.5,  agg2=.6)
    L2 agg1-rr1    192.0.2.8/30   (agg1=.9,   rr1=.10)
    L3 agg2-rr2    192.0.2.12/30  (agg2=.13,  rr2=.14)
    L4 rr1-rr2     192.0.2.16/30  (rr1=.17,   rr2=.18)
    L5 agg1-agg2   192.0.2.20/30  (agg1=.21,  agg2=.22)

OSPF: a single `router ospf` per node, every transit /30 and the loopback /32 placed
in area 0 via `ip ospf area 0` on the interface (FRR's modern idiomatic form — no
classful `network` masks). Each `router ospf` carries `passive-interface lo` so no
adjacency is attempted out the stub /32 (idiomatic; does not affect /32
advertisement — the loopback is still placed in area 0 and advertised). The p2p
links use `ip ospf network point-to-point` so the /30 is advertised as a transit
link with a single neighbor (idiomatic for /30 fabric links; keeps Batfish's OSPF
adjacency model unambiguous).

Verified on live Batfish (batfish/allinone:nethelm, 127.0.0.1:9996/9997): see the
header of scenario_ospf_core6.py for the PRE-state proof (sessions up, every
loopback present as an OSPF route in every node's RIB, and the customer-prefix iBGP
next-hop resolving via an OSPF route — NOT static/connected). DO NOT edit the config
text without re-verifying; ground truth depends on it. Treat as frozen once committed.
"""

from __future__ import annotations

NODES = ["rr1", "rr2", "agg1", "agg2", "edge1", "edge2"]

# Loopback (== OSPF router-id == bgp router-id) for each node.
LOOPBACK_IP = {
    "rr1": "10.0.0.1", "rr2": "10.0.0.2",
    "agg1": "10.0.0.3", "agg2": "10.0.0.4",
    "edge1": "10.0.0.5", "edge2": "10.0.0.6",
}

# The customer prefix edge2 originates into BGP (NO static, NO `network` backup
# anywhere — reachability rides iBGP, and the iBGP next-hop rides OSPF).
CUSTOMER_PREFIX = "203.0.113.0/24"
CUSTOMER_IP = "203.0.113.1"  # a host inside it, for traceroute

# D2 watch set: the customer /24 + every loopback. The loopbacks are negative
# controls (a model that false-positives on a surviving loopback loses precision).
WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32",
    "10.0.0.4/32", "10.0.0.5/32", "10.0.0.6/32",
    CUSTOMER_PREFIX,
]

# Physical links (lower node listed first), for the topology record / clab render.
LINKS = [
    ("edge1", "eth1", "agg1", "eth1"),  # L0  192.0.2.0/30
    ("edge2", "eth1", "agg2", "eth1"),  # L1  192.0.2.4/30
    ("agg1", "eth2", "rr1", "eth1"),    # L2  192.0.2.8/30
    ("agg2", "eth2", "rr2", "eth1"),    # L3  192.0.2.12/30
    ("rr1", "eth2", "rr2", "eth2"),     # L4  192.0.2.16/30
    ("agg1", "eth3", "agg2", "eth3"),   # L5  192.0.2.20/30
]

# The change target for the scenario (the node whose OSPF link is cut).
CHANGE_TARGET = "agg1"


# --------------------------------------------------------------------------- #
# Per-node FRR configs (CUMULUS_CONCATENATED format; frr version 10.6.1). Every
# loopback /32 + every transit /30 is in OSPF area 0; iBGP over loopbacks with
# next-hop-self on the RRs. NO `ip route` anywhere — grep these files and you will
# find zero static routes (the crutch-killer invariant).
# --------------------------------------------------------------------------- #

_RR1 = """rr1

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.1/32

auto eth1
iface eth1 inet static
    address 192.0.2.10/30

auto eth2
iface eth2 inet static
    address 192.0.2.17/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname rr1
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.1/32
 ip ospf area 0
!
interface eth1
 ip address 192.0.2.10/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface eth2
 ip address 192.0.2.17/30
 ip ospf area 0
 ip ospf network point-to-point
!
router ospf
 ospf router-id 10.0.0.1
 passive-interface lo
!
router bgp 65000
 bgp router-id 10.0.0.1
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 10.0.0.4 remote-as 65000
 neighbor 10.0.0.4 update-source lo
 neighbor 10.0.0.5 remote-as 65000
 neighbor 10.0.0.5 update-source lo
 neighbor 10.0.0.6 remote-as 65000
 neighbor 10.0.0.6 update-source lo
 !
 address-family ipv4 unicast
  neighbor 10.0.0.3 route-reflector-client
  neighbor 10.0.0.3 next-hop-self
  neighbor 10.0.0.4 route-reflector-client
  neighbor 10.0.0.4 next-hop-self
  neighbor 10.0.0.5 route-reflector-client
  neighbor 10.0.0.5 next-hop-self
  neighbor 10.0.0.6 route-reflector-client
  neighbor 10.0.0.6 next-hop-self
 exit-address-family
!
line vty
!
"""

_RR2 = """rr2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.2/32

auto eth1
iface eth1 inet static
    address 192.0.2.14/30

auto eth2
iface eth2 inet static
    address 192.0.2.18/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname rr2
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.2/32
 ip ospf area 0
!
interface eth1
 ip address 192.0.2.14/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface eth2
 ip address 192.0.2.18/30
 ip ospf area 0
 ip ospf network point-to-point
!
router ospf
 ospf router-id 10.0.0.2
 passive-interface lo
!
router bgp 65000
 bgp router-id 10.0.0.2
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 10.0.0.4 remote-as 65000
 neighbor 10.0.0.4 update-source lo
 neighbor 10.0.0.5 remote-as 65000
 neighbor 10.0.0.5 update-source lo
 neighbor 10.0.0.6 remote-as 65000
 neighbor 10.0.0.6 update-source lo
 !
 address-family ipv4 unicast
  neighbor 10.0.0.3 route-reflector-client
  neighbor 10.0.0.3 next-hop-self
  neighbor 10.0.0.4 route-reflector-client
  neighbor 10.0.0.4 next-hop-self
  neighbor 10.0.0.5 route-reflector-client
  neighbor 10.0.0.5 next-hop-self
  neighbor 10.0.0.6 route-reflector-client
  neighbor 10.0.0.6 next-hop-self
 exit-address-family
!
line vty
!
"""

_AGG1 = """agg1

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.2/30

auto eth2
iface eth2 inet static
    address 192.0.2.9/30

auto eth3
iface eth3 inet static
    address 192.0.2.21/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname agg1
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.3/32
 ip ospf area 0
!
interface eth1
 ip address 192.0.2.2/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface eth2
 ip address 192.0.2.9/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface eth3
 ip address 192.0.2.21/30
 ip ospf area 0
 ip ospf network point-to-point
!
router ospf
 ospf router-id 10.0.0.3
 passive-interface lo
!
router bgp 65000
 bgp router-id 10.0.0.3
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
 exit-address-family
!
line vty
!
"""

_AGG2 = """agg2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.4/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto eth2
iface eth2 inet static
    address 192.0.2.13/30

auto eth3
iface eth3 inet static
    address 192.0.2.22/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname agg2
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.4/32
 ip ospf area 0
!
interface eth1
 ip address 192.0.2.6/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface eth2
 ip address 192.0.2.13/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface eth3
 ip address 192.0.2.22/30
 ip ospf area 0
 ip ospf network point-to-point
!
router ospf
 ospf router-id 10.0.0.4
 passive-interface lo
!
router bgp 65000
 bgp router-id 10.0.0.4
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
 exit-address-family
!
line vty
!
"""

_EDGE1 = """edge1

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.5/32

auto eth1
iface eth1 inet static
    address 192.0.2.1/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname edge1
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.5/32
 ip ospf area 0
!
interface eth1
 ip address 192.0.2.1/30
 ip ospf area 0
 ip ospf network point-to-point
!
router ospf
 ospf router-id 10.0.0.5
 passive-interface lo
!
router bgp 65000
 bgp router-id 10.0.0.5
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
 exit-address-family
!
line vty
!
"""

_EDGE2 = """edge2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.6/32

auto eth1
iface eth1 inet static
    address 192.0.2.5/30

auto dum0
iface dum0 inet static
    address 203.0.113.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname edge2
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.6/32
 ip ospf area 0
!
interface eth1
 ip address 192.0.2.5/30
 ip ospf area 0
 ip ospf network point-to-point
!
interface dum0
 ip address 203.0.113.1/24
!
router ospf
 ospf router-id 10.0.0.6
 passive-interface lo
!
router bgp 65000
 bgp router-id 10.0.0.6
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
  network 203.0.113.0/24
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified ospf_core6 baseline)."""
    return {
        "rr1": _RR1, "rr2": _RR2,
        "agg1": _AGG1, "agg2": _AGG2,
        "edge1": _EDGE1, "edge2": _EDGE2,
    }
