"""The `ipc_fanout` baseline: a route-reflector with FOUR clients (Class-1, #3).

This baseline exists to give the Class-1 generator a DIFFERENT blast STRUCTURE
from the flagship S-IPC-01: instead of a single client losing a single prefix,
here the route reflector (r1) advertises ONE customer prefix to FOUR clients, and
a "cleanup" filter applied to ALL FOUR client sessions withdraws that prefix from
every client at once. The blast radius is therefore the SAME prefix on N=4 nodes
(a different *affected-node set* and a different D2/D3 cardinality), not 1 node.

Topology (a star; r1 is the RR, r2..r5 are clients; r5 originates)::

            r2   r3   r4
              \  |  /
               r1 (RR)
                |
               r5  (client, origin of the customer prefix)

Deterministic addressing (docs/authoring_topologies_and_scenarios.md §1):
  * node rX  -> loopback 10.0.0.X/32 -> bgp router-id 10.0.0.X
  * links in fixed order (lower node first):
      i0 r1-r2  192.0.2.0/30  (r1=.1, r2=.2)
      i1 r1-r3  192.0.2.4/30  (r1=.5, r3=.6)
      i2 r1-r4  192.0.2.8/30  (r1=.9, r4=.10)
      i3 r1-r5  192.0.2.12/30 (r1=.13, r5=.14)
  * iBGP: r2..r5 are route-reflector-clients of r1; r1 next-hop-self to all.
    Clients do not peer with each other (r1 is sole transit) -> the customer
    prefix reaches r2/r3/r4 ONLY via r1's advertisement.

Two prefix classes (same doctrine as ipc3):
  * Loopbacks 10.0.0.{1..5}/32 -- every node has a STATIC route to every other
    loopback (far-side link IP; r2..r5 reach each other via r1). BGP-independent,
    so sessions stay up and the network "looks fine."
  * Customer prefix 203.0.113.0/24 -- originated by r5, NO static backup anywhere.
    Its reachability on r2/r3/r4 depends ENTIRELY on r1's advertisement. This is
    the prefix the all-clients CLEANUP filter withdraws.

The change (the #3 generator instance): the outbound CLEANUP_OUT prefix-list +
TO_CLIENTS_OUT route-map (permits 10/8 + 192.0.2.0/24, implicit-denies the
customer prefix) is attached to r1's sessions toward r2, r3 AND r4 (NOT r5: r5 is
the origin/transit, leaving it lets the prefix survive in r1's own RIB so the
withdrawal is purely an advertisement-suppression on the three leaf clients).
Result: 203.0.113.0/24 is lost on r2, r3, r4 -> D2/D3 cardinality = 3 nodes.

Verified on live Batfish (batfish/allinone, 127.0.0.1:9997) -- see the generator
verification block. Treat this file as frozen once committed.
"""

from __future__ import annotations

NODES = ["r1", "r2", "r3", "r4", "r5"]

LOOPBACK_IP = {
    "r1": "10.0.0.1", "r2": "10.0.0.2", "r3": "10.0.0.3",
    "r4": "10.0.0.4", "r5": "10.0.0.5",
}

CUSTOMER_PREFIX = "203.0.113.0/24"
CUSTOMER_IP = "203.0.113.1"

# r5 originates; r2/r3/r4 are the leaf clients the filter is applied toward.
ORIGIN = "r5"
LEAF_CLIENTS = ["r2", "r3", "r4"]

WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32",
    "10.0.0.4/32", "10.0.0.5/32", "203.0.113.0/24",
]

LINKS = [
    ("r1", "eth1", "r2", "eth1"),
    ("r1", "eth2", "r3", "eth1"),
    ("r1", "eth3", "r4", "eth1"),
    ("r1", "eth4", "r5", "eth1"),
]

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

auto eth3
iface eth3 inet static
    address 192.0.2.9/30

auto eth4
iface eth4 inet static
    address 192.0.2.13/30

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
interface eth3
 ip address 192.0.2.9/30
!
interface eth4
 ip address 192.0.2.13/30
!
ip route 10.0.0.2/32 192.0.2.2
ip route 10.0.0.3/32 192.0.2.6
ip route 10.0.0.4/32 192.0.2.10
ip route 10.0.0.5/32 192.0.2.14
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
 !
 address-family ipv4 unicast
  neighbor 10.0.0.2 route-reflector-client
  neighbor 10.0.0.2 next-hop-self
  neighbor 10.0.0.3 route-reflector-client
  neighbor 10.0.0.3 next-hop-self
  neighbor 10.0.0.4 route-reflector-client
  neighbor 10.0.0.4 next-hop-self
  neighbor 10.0.0.5 route-reflector-client
  neighbor 10.0.0.5 next-hop-self
 exit-address-family
!
line vty
!
"""


def _leaf_config(node: str, x: int, near: str, far: str) -> str:
    """A leaf client rX (r2/r3/r4): one link to r1, statics to every loopback."""
    statics = "\n".join(
        f"ip route 10.0.0.{y}/32 {far}"
        for y in (1, 2, 3, 4, 5) if y != x
    )
    return f"""{node}

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.{x}/32

auto eth1
iface eth1 inet static
    address {near}/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname {node}
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.{x}/32
!
interface eth1
 ip address {near}/30
!
{statics}
!
router bgp 65000
 bgp router-id 10.0.0.{x}
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


# r2 near=.2 far=.1 ; r3 near=.6 far=.5 ; r4 near=.10 far=.9
_R2 = _leaf_config("r2", 2, "192.0.2.2", "192.0.2.1")
_R3 = _leaf_config("r3", 3, "192.0.2.6", "192.0.2.5")
_R4 = _leaf_config("r4", 4, "192.0.2.10", "192.0.2.9")

# r5 is the origin: like a leaf but with a dummy interface + network statement.
_R5 = """r5

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.5/32

auto eth1
iface eth1 inet static
    address 192.0.2.14/30

auto dum0
iface dum0 inet static
    address 203.0.113.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname r5
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.5/32
!
interface eth1
 ip address 192.0.2.14/30
!
interface dum0
 ip address 203.0.113.1/24
!
ip route 10.0.0.1/32 192.0.2.13
ip route 10.0.0.2/32 192.0.2.13
ip route 10.0.0.3/32 192.0.2.13
ip route 10.0.0.4/32 192.0.2.13
!
router bgp 65000
 bgp router-id 10.0.0.5
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 !
 address-family ipv4 unicast
  network 203.0.113.0/24
  neighbor 10.0.0.1 next-hop-self
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified ipc_fanout baseline)."""
    return {"r1": _R1, "r2": _R2, "r3": _R3, "r4": _R4, "r5": _R5}
