"""The `lp_waypoint` baseline: a BGP topology for the LOCAL_PREF-driven D4 class.

Purpose (spine class 5, "local-pref/MED empty-blast trap" in
docs/oracle_determinism_spec_v1.md): demonstrate a blast radius that is a pure
WAYPOINT (D4) violation driven by a BGP **attribute** (LOCAL_PREF) change — the
DOCUMENTED LLM failure mode (knowledge/corpus/noc/network_change_management.md:
"Predicting session loss for LOCAL_PREF changes (sessions don't drop on LP
changes)"). The trap: a naive model predicts a D1 session drop and/or D2/D3 loss;
the truth is D1=D2=D3=∅ and ONLY D4 fires.

This is mechanistically DISTINCT from `waypoint4` (which reroutes via a STATIC
route edit). Here the egress choice is a BGP best-path decision, flipped by a
LOCAL_PREF change, with NO session and NO prefix lost.

Topology (one internal AS65000 + one external customer AS65004)::

                 iBGP (full mesh, over loopbacks)
        +---------------------------------------------+
        |                                             |
      src ----eth1/eth1---- way ----eth2/eth1(eBGP)-- dst   (the WAY/inspection path)
       |  192.0.2.0/30       |        192.0.2.8/30     |
       |                     +----------iBGP-----------+      203.0.113.0/24
       |                                               |      (customer prefix,
       +----eth2/eth1------- alt ---eth2/eth2(eBGP)----+       dual-homed to both
          192.0.2.4/30              192.0.2.12/30              way and alt)

  * src, way, alt are AS65000 (iBGP full mesh over loopbacks, update-source lo).
  * dst is AS65004; it originates 203.0.113.0/24 and is DUAL-HOMED via eBGP to
    BOTH way (link 192.0.2.8/30) and alt (link 192.0.2.12/30).
  * way and alt re-advertise the customer prefix into iBGP. The advertised
    next-hop is the dst-side eBGP link IP (192.0.2.10 via way, 192.0.2.14 via
    alt); src resolves both with static routes to those egress-link /30s (the
    static-backup doctrine of the addressing scheme). src therefore has a route
    via EACH egress and chooses ONE by best-path. (No `next-hop-self`: Batfish's
    FRR model leaves the eBGP next-hop on the iBGP-advertised route, so resolving
    the real next-hop at src is the deterministic, Batfish-faithful choice.)

Pre-state steering (the "looks fine" steady state):
  * way applies an inbound eBGP route-map (FROM_DST_IN) that sets
    `local-preference 200` on ALL routes learned from dst (no match clause — so
    dst's loopback is covered too, which keeps best-path strict and avoids a tie).
  * alt applies an inbound eBGP route-map (FROM_DST_IN) that sets
    `local-preference 100` (the FRR default, made explicit for symmetry/clarity).
  * At src, LOCAL_PREF 200 (via way) strictly beats 100 (via alt) — the FIRST BGP
    best-path attribute (RFC 4271 §9.1.1 step 1; "weight" is Cisco-only, not modeled).
    So src installs the WAY path: src->dst
    transits `way`. STRICT preference: 200 != 100, so there is NO equal-cost tie
    and NO ECMP (maximum-paths is the default 1). Deterministic chosen egress.

Addressing (docs/authoring_topologies_and_scenarios.md §1):
  loopbacks 10.0.0.{1..4}/32 == router-ids; p2p links 192.0.2.0/24 in /30s,
  fixed order (lower node first):
    link0 src-way 192.0.2.0/30  (src=.1, way=.2)
    link1 src-alt 192.0.2.4/30  (src=.5, alt=.6)
    link2 way-dst 192.0.2.8/30  (way=.9, dst=.10)
    link3 alt-dst 192.0.2.12/30 (alt=.13, dst=.14)

Why D2/D3 stay ∅ (the destination is ALWAYS reachable, just via a different
egress): the customer /24 is originated by dst on a dummy dum0 host
(203.0.113.1/24) and advertised over BOTH egress paths, so src always has a best
route and a working data path to 203.0.113.1 — pre AND post. Only WHICH egress
(and hence whether `way` is on the path) changes. Verified (Batfish): pre best
path nh=192.0.2.10 (way) LP=200, trace src->way->dst; post best path nh=192.0.2.14
(alt) LP=300, trace src->alt->dst. Exactly one accepted trace family each.

Strict-preference / determinism guarantee per oracle_determinism_spec_v1.md class
5: a STRICT LOCAL_PREF gap (200 vs 100 pre; 100 vs 300 post) means a single best
path at src in both snapshots — no ECMP, no chosen-path ambiguity. Router-ids are
pinned to loopbacks. STATIC-DETERMINISTIC; D4 is scored as the all-traces-transit
invariant by ExtendedOracle._waypoint_diff.

Batfish-parseable FRR (CUMULUS_CONCATENATED, frr version 10.6.1). Treat this file
as frozen once verified.
"""

from __future__ import annotations

NODES = ["src", "way", "alt", "dst"]

LOOPBACK_IP = {"src": "10.0.0.1", "way": "10.0.0.2", "alt": "10.0.0.3", "dst": "10.0.0.4"}

ASN = {"src": 65000, "way": 65000, "alt": 65000, "dst": 65004}

# The customer prefix dst originates and a host inside it to probe.
CUSTOMER_PREFIX = "203.0.113.0/24"
CUSTOMER_IP = "203.0.113.1"

# D2 watch set: the customer /24 + all loopbacks (negative controls).
WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "10.0.0.4/32",
    CUSTOMER_PREFIX,
]

# (a_node, a_intf, b_node, b_intf) — fixed order, lower node first.
LINKS = [
    ("src", "eth1", "way", "eth1"),
    ("src", "eth2", "alt", "eth1"),
    ("way", "eth2", "dst", "eth1"),
    ("alt", "eth2", "dst", "eth2"),
]

# The intent the change violates: traffic from `src` to the customer host MUST
# transit `way` (the inspection/scrubbing node). Probed at the /32 host so the
# traceroute has a real connected accept at dst (the bare /24 .0 is not a host).
WAYPOINT_INTENTS = [("src", CUSTOMER_IP + "/32", "way")]

# D3 proof set: src must STILL reach the customer host post-change (just off-path).
REACHABILITY_FLOWS = [("src", CUSTOMER_IP + "/32")]

CHANGE_TARGET = "alt"


_SRC = """src

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.1/32

auto eth1
iface eth1 inet static
    address 192.0.2.1/30

auto eth2
iface eth2 inet static
    address 192.0.2.5/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname src
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.1/32
!
interface eth1
 ip address 192.0.2.1/30
!
interface eth2
 ip address 192.0.2.5/30
!
ip route 10.0.0.2/32 192.0.2.2
ip route 10.0.0.3/32 192.0.2.6
ip route 192.0.2.8/30 192.0.2.2
ip route 192.0.2.12/30 192.0.2.6
!
router bgp 65000
 bgp router-id 10.0.0.1
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 !
 address-family ipv4 unicast
  network 10.0.0.1/32
 exit-address-family
!
line vty
!
"""


_WAY = """way

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.2/32

auto eth1
iface eth1 inet static
    address 192.0.2.2/30

auto eth2
iface eth2 inet static
    address 192.0.2.9/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname way
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.2/32
!
interface eth1
 ip address 192.0.2.2/30
!
interface eth2
 ip address 192.0.2.9/30
!
ip route 10.0.0.1/32 192.0.2.1
ip route 10.0.0.3/32 192.0.2.1
!
route-map FROM_DST_IN permit 10
 set local-preference 200
!
router bgp 65000
 bgp router-id 10.0.0.2
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 192.0.2.10 remote-as 65004
 !
 address-family ipv4 unicast
  network 10.0.0.2/32
  neighbor 192.0.2.10 route-map FROM_DST_IN in
 exit-address-family
!
line vty
!
"""


_ALT = """alt

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto eth2
iface eth2 inet static
    address 192.0.2.13/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname alt
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.3/32
!
interface eth1
 ip address 192.0.2.6/30
!
interface eth2
 ip address 192.0.2.13/30
!
ip route 10.0.0.1/32 192.0.2.5
ip route 10.0.0.2/32 192.0.2.5
!
route-map FROM_DST_IN permit 10
 set local-preference 100
!
router bgp 65000
 bgp router-id 10.0.0.3
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 192.0.2.14 remote-as 65004
 !
 address-family ipv4 unicast
  network 10.0.0.3/32
  neighbor 192.0.2.14 route-map FROM_DST_IN in
 exit-address-family
!
line vty
!
"""


_DST = """dst

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.4/32

auto eth1
iface eth1 inet static
    address 192.0.2.10/30

auto eth2
iface eth2 inet static
    address 192.0.2.14/30

auto dum0
iface dum0 inet static
    address 203.0.113.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname dst
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.4/32
!
interface eth1
 ip address 192.0.2.10/30
!
interface eth2
 ip address 192.0.2.14/30
!
interface dum0
 ip address 203.0.113.1/24
!
router bgp 65004
 bgp router-id 10.0.0.4
 neighbor 192.0.2.9 remote-as 65000
 neighbor 192.0.2.13 remote-as 65000
 !
 address-family ipv4 unicast
  network 10.0.0.4/32
  network 203.0.113.0/24
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified lp_waypoint baseline)."""
    return {"src": _SRC, "way": _WAY, "alt": _ALT, "dst": _DST}
