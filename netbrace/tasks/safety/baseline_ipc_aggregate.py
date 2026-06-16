"""The `ipc_aggregate` baseline: aggregate + more-specifics origin (Class-1, #4).

This baseline gives the Class-1 generator a blast STRUCTURE distinct from the
flagship (S-IPC-01), the has-static sibling, and the fanout (S-IPC-02): an
**aggregation router** (r3) that advertises a supernet (the /24 aggregate) AND two
more-specific /25 prefixes that pin traffic for multihoming/traffic-engineering
reasons. A downstream "cleanup" filter on the RR (r1) toward the client (r2) can
then permit the aggregate while implicit-denying the more-specifics. The DISTINCT,
interesting structure: the **aggregate survives** on the client (so coarse
reachability to an address inside it can still succeed via the supernet) while the
**more-specifics are withdrawn** from the client's RIB. This is the "looks fine
because the /24 is still there" trap — a different answer shape than the flagship.

Topology (a line; r1 is the route reflector, r2 is the client, r3 originates)::

      r2 ───── r1 ───── r3
    (client)  (RR)   (aggregation router / origin)

Deterministic addressing (per docs/authoring_topologies_and_scenarios.md §1):
  * node rX  → loopback 10.0.0.X/32 → bgp router-id 10.0.0.X
  * link r1–r2 = 192.0.2.0/30 (r1=.1, r2=.2); link r1–r3 = 192.0.2.4/30 (r1=.5, r3=.6)
  * iBGP: r2 and r3 are route-reflector-clients of r1 (next-hop-self toward both).
    r2 and r3 do NOT peer with each other — r1 is the sole transit between them.

Three prefix CLASSES, deliberately distinct:
  * **Loopbacks** 10.0.0.{1,2,3}/32 — every node has a STATIC route to each other
    loopback (far-side IP of the direct link, via r1 for the r2↔r3 pair). Loopback
    reachability is BGP-INDEPENDENT, so the iBGP sessions stay up and the network
    "looks fine" even when customer prefixes are withdrawn.
  * **Aggregate** 203.0.113.0/24 — the supernet r3 advertises. Backed by a discard
    static (`ip route 203.0.113.0/24 Null0`), which is exactly how a real
    aggregation router pins a supernet so `network 203.0.113.0/24` can originate it.
    NO static backup for it on r2 — its reachability on r2 depends on BGP alone.
  * **More-specifics** 203.0.113.0/25 and 203.0.113.128/25 — the two halves r3
    pins as separate BGP routes (multihoming / TE). Each is a CONNECTED route on a
    dummy customer-facing interface (dum0=.1/25, dum1=.129/25), so `network
    203.0.113.0/25` / `network 203.0.113.128/25` originate them. NO static backup
    on r2. These are the prefixes the downstream CLEANUP filter withdraws.

Why this is NOT just ipc3 with extra prefixes: in ipc3 the customer prefix is the
ONLY route to that address space, so withdrawing it produces a clean NO_ROUTE
(D2+D3 both fire). Here the aggregate COVERS the same address space — so when the
/25s are withdrawn from r2, D2 fires (the /25 BEST routes leave r2's RIB) but D3
(reachability to an address inside a /25) may be SILENT because the surviving /24
still resolves it. Whether D3/D4 fire is an EMPIRICAL question answered by the
oracle; declare only what fires.

Verified on live Batfish (batfish/allinone, 127.0.0.1:9997), 2026-06-08 — see the
scenario module's verification block. Treat this file as frozen once committed.
"""

from __future__ import annotations

NODES = ["r1", "r2", "r3"]

# Loopback (and BGP router-id) IP for each node.
LOOPBACK_IP = {"r1": "10.0.0.1", "r2": "10.0.0.2", "r3": "10.0.0.3"}

# The aggregate (supernet) and the two more-specific halves r3 originates.
AGGREGATE_PREFIX = "203.0.113.0/24"
SPECIFIC_LOW = "203.0.113.0/25"     # covers 203.0.113.0 .. .127
SPECIFIC_HIGH = "203.0.113.128/25"  # covers 203.0.113.128 .. .255

# Representative addresses for traceroute probes (one inside each /25, plus one
# that exercises the aggregate path explicitly).
IP_IN_LOW = "203.0.113.10"     # inside 203.0.113.0/25
IP_IN_HIGH = "203.0.113.200"   # inside 203.0.113.128/25
IP_IN_AGG = "203.0.113.1"      # inside the /24 aggregate (also inside the low /25)

# Prefixes scored for the route diff (D2): the aggregate + both /25 more-specifics
# + the three loopbacks (negative controls). The /25s are the ones the CLEANUP
# filter withdraws; the aggregate and loopbacks must NOT be collateral damage.
WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32",
    AGGREGATE_PREFIX, SPECIFIC_LOW, SPECIFIC_HIGH,
]

# Physical links (lower node number first), for the topology record / clab render.
LINKS = [
    ("r1", "eth1", "r2", "eth1"),
    ("r1", "eth2", "r3", "eth1"),
]

# The RR (r1) is the change target.
CHANGE_TARGET = "r1"

_R1 = """r1

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
hostname r1
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
!
router bgp 65000
 bgp router-id 10.0.0.1
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 !
 address-family ipv4 unicast
  neighbor 10.0.0.2 route-reflector-client
  neighbor 10.0.0.2 next-hop-self
  neighbor 10.0.0.3 route-reflector-client
  neighbor 10.0.0.3 next-hop-self
 exit-address-family
!
line vty
!
"""

_R2 = """r2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.2/32

auto eth1
iface eth1 inet static
    address 192.0.2.2/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname r2
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
ip route 10.0.0.1/32 192.0.2.1
ip route 10.0.0.3/32 192.0.2.1
!
router bgp 65000
 bgp router-id 10.0.0.2
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 !
 address-family ipv4 unicast
  neighbor 10.0.0.1 next-hop-self
 exit-address-family
!
line vty
!
"""

# r3 is the aggregation router: a discard static backs the /24 aggregate, and two
# dummy customer-facing interfaces (dum0, dum1) back the two /25 more-specifics as
# connected routes. All three are advertised via `network` statements.
_R3 = """r3

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto dum0
iface dum0 inet static
    address 203.0.113.1/25

auto dum1
iface dum1 inet static
    address 203.0.113.129/25

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname r3
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
interface dum0
 ip address 203.0.113.1/25
!
interface dum1
 ip address 203.0.113.129/25
!
ip route 10.0.0.1/32 192.0.2.5
ip route 10.0.0.2/32 192.0.2.5
ip route 203.0.113.0/24 Null0
!
router bgp 65000
 bgp router-id 10.0.0.3
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 !
 address-family ipv4 unicast
  network 203.0.113.0/24
  network 203.0.113.0/25
  network 203.0.113.128/25
  neighbor 10.0.0.1 next-hop-self
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified ipc_aggregate baseline)."""
    return {"r1": _R1, "r2": _R2, "r3": _R3}
