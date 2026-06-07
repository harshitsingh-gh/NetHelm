"""The verified `square4` baseline: 4 FRR routers, iBGP full mesh, AS 65000.

These configs are copied VERBATIM from the verified lab snapshot
(runs/2026-05-27_batfish_frrsq/snapshot/configs/) which Batfish parses cleanly
and which converges to 12 ESTABLISHED BGP sessions. DO NOT edit the config text
without re-verifying in Batfish — ground-truth correctness depends on it.

Topology facts (used by the generator):
  * node rX has loopback 10.0.0.X/32 and BGP router-id 10.0.0.X.
  * iBGP full mesh: every rX peers with the other three via their loopback IPs
    (update-source lo, next-hop-self).
  * each rX originates its own loopback with `network 10.0.0.X/32`.
  * every router has STATIC routes to all other loopbacks (so loopback data-plane
    reachability does NOT depend on BGP — this is intentional and is what makes
    "does the model know the static route is a backup?" a real question).
"""

from __future__ import annotations

NODES = ["r1", "r2", "r3", "r4"]

# Loopback (and BGP neighbor) IP for each node.
LOOPBACK_IP = {"r1": "10.0.0.1", "r2": "10.0.0.2", "r3": "10.0.0.3", "r4": "10.0.0.4"}

# The four watched prefixes for the route diff (all loopbacks).
WATCHED_PREFIXES = ["10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "10.0.0.4/32"]

# Physical links (for the topology record / future containerlab rendering).
LINKS = [
    ("r1", "eth1", "r2", "eth1"),
    ("r1", "eth2", "r3", "eth1"),
    ("r1", "eth3", "r4", "eth1"),
    ("r2", "eth2", "r3", "eth2"),
    ("r2", "eth3", "r4", "eth2"),
    ("r3", "eth3", "r4", "eth3"),
]

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
ip route 10.0.0.2/32 192.0.2.2
ip route 10.0.0.3/32 192.0.2.6
ip route 10.0.0.4/32 192.0.2.10
!
router bgp 65000
 bgp router-id 10.0.0.1
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 10.0.0.2 next-hop-self
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 10.0.0.3 next-hop-self
 neighbor 10.0.0.4 remote-as 65000
 neighbor 10.0.0.4 update-source lo
 neighbor 10.0.0.4 next-hop-self
 !
 address-family ipv4 unicast
  network 10.0.0.1/32
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

auto eth2
iface eth2 inet static
    address 192.0.2.13/30

auto eth3
iface eth3 inet static
    address 192.0.2.17/30

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
interface eth2
 ip address 192.0.2.13/30
!
interface eth3
 ip address 192.0.2.17/30
!
ip route 10.0.0.1/32 192.0.2.1
ip route 10.0.0.3/32 192.0.2.14
ip route 10.0.0.4/32 192.0.2.18
!
router bgp 65000
 bgp router-id 10.0.0.2
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.1 next-hop-self
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 10.0.0.3 next-hop-self
 neighbor 10.0.0.4 remote-as 65000
 neighbor 10.0.0.4 update-source lo
 neighbor 10.0.0.4 next-hop-self
 !
 address-family ipv4 unicast
  network 10.0.0.2/32
 exit-address-family
!
line vty
!
"""

_R3 = """r3

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto eth2
iface eth2 inet static
    address 192.0.2.14/30

auto eth3
iface eth3 inet static
    address 192.0.2.21/30

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
interface eth2
 ip address 192.0.2.14/30
!
interface eth3
 ip address 192.0.2.21/30
!
ip route 10.0.0.1/32 192.0.2.5
ip route 10.0.0.2/32 192.0.2.13
ip route 10.0.0.4/32 192.0.2.22
!
router bgp 65000
 bgp router-id 10.0.0.3
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.1 next-hop-self
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 10.0.0.2 next-hop-self
 neighbor 10.0.0.4 remote-as 65000
 neighbor 10.0.0.4 update-source lo
 neighbor 10.0.0.4 next-hop-self
 !
 address-family ipv4 unicast
  network 10.0.0.3/32
 exit-address-family
!
line vty
!
"""

_R4 = """r4

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.4/32

auto eth1
iface eth1 inet static
    address 192.0.2.10/30

auto eth2
iface eth2 inet static
    address 192.0.2.18/30

auto eth3
iface eth3 inet static
    address 192.0.2.22/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname r4
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
 ip address 192.0.2.18/30
!
interface eth3
 ip address 192.0.2.22/30
!
ip route 10.0.0.1/32 192.0.2.9
ip route 10.0.0.2/32 192.0.2.17
ip route 10.0.0.3/32 192.0.2.21
!
router bgp 65000
 bgp router-id 10.0.0.4
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.1 next-hop-self
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 neighbor 10.0.0.2 next-hop-self
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 10.0.0.3 next-hop-self
 !
 address-family ipv4 unicast
  network 10.0.0.4/32
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified square4 baseline)."""
    return {"r1": _R1, "r2": _R2, "r3": _R3, "r4": _R4}
