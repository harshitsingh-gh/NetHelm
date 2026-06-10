"""The `mgmt_lockout` baseline: a 4-node iBGP route-reflector spine, AS 65000,
modeling a NOC jump-host that reaches TWO managed devices' MANAGEMENT addresses
purely over the production control plane (an *in-band* OOB path — the exact
dependency that turned Facebook-Oct-2021, AWS-us-east-1-Dec-2021, Rogers-Jul-2022
and Cloudflare-Jun-2022 into multi-hour recoveries).

RELATIONSHIP TO `ipc` (read this first — it is the point of the class).
This baseline reuses the SAME mechanism as the `ipc` flagship: an outbound iBGP
prefix-list "cleanup" whose implicit deny-all silently withdraws a prefix from a
downstream peer while every BGP session stays ESTABLISHED (D1 = ∅). It is NOT a
new mechanism. Its distinct value is the GRADED SURFACE: the withdrawn prefixes
are the managed devices' MANAGEMENT subnets, and the scenario is scored against a
stated "the NOC jump-host MUST retain management reachability to every device"
INTENT (the D10 dimension). A model that merely lists a reachability loss but does
NOT recognize it as a violation of that management-reachability intent misses D10.
This is the deliberate sibling pattern already used by `ipc_static` (same Class-1
withdrawal, value is the D9 control-plane dimension) — here the value is D10.

The trap a customer-centric review walks into: a change can leave EVERY customer
prefix and EVERY BGP session intact (D1 = ∅, D2 = ∅, with the customer prefix and
the loopbacks WATCHED and provably surviving) yet remove the only path the NOC
uses to reach each device — so a model reasoning "no customer prefixes affected,
no sessions dropped -> safe" is catastrophically wrong, and a model that flags the
reachability loss but not the management-intent violation is incomplete.

Topology (a star around `core`, the route reflector / aggregation router)::

                 jump  (NOC jump-host)
                  │
      edge ───── core ───── edge2
   (managed dev #1)│  (managed dev #2)
                 (RR)

Deterministic addressing (per docs/authoring_topologies_and_scenarios.md §1):
  * node loopbacks: jump=10.0.0.1, core=10.0.0.2, edge=10.0.0.3, edge2=10.0.0.4
    (== bgp router-id)
  * link jump–core  = 192.0.2.0/30 (jump=.1,  core=.2)
  * link core–edge  = 192.0.2.4/30 (core=.5,  edge=.6)
  * link core–edge2 = 192.0.2.8/30 (core=.9,  edge2=.10)
  * iBGP: jump, edge and edge2 are route-reflector-clients of core (next-hop-self
    toward all). The clients do NOT peer directly — core is the sole transit.

Three prefix CLASSES, deliberately distinct:
  * **Loopbacks** 10.0.0.{1,2,3,4}/32 — every node has a STATIC route to each other
    loopback. Loopback reachability is therefore BGP-INDEPENDENT (the square4 /
    ipc3 doctrine): the iBGP sessions stay ESTABLISHED no matter what the change
    does to advertisements, so D1 = ∅ and "the backbone looks fine." The loopbacks
    are WATCHED (D2 negative control: they must survive).
  * **Customer/data prefix** 203.0.113.0/24 — originated by `edge` (dummy iface),
    advertised edge -> core -> jump. The NEGATIVE CONTROL: the change keeps
    advertising it, so it stays in every RIB (it is WATCHED, D2 = ∅) and stays
    reachable. This is what makes the trap convincing — the customer/data plane is
    provably untouched, AND a model that false-positives on it loses D2 precision.
  * **Management prefixes** 172.16.0.0/24 (edge, mgmt-IP 172.16.0.1) and
    172.16.1.0/24 (edge2, mgmt-IP 172.16.1.1) — each device's MANAGEMENT subnet,
    originated by that device (dummy iface), advertised dev -> core -> jump.
    **NO static backup ANYWHERE** (in-band OOB: the NOC's only path to each device's
    mgmt-IP is this BGP advertisement). These are the prefixes the change stops
    advertising toward `jump`, locking the NOC out of BOTH devices. There are TWO
    of them so the ground truth has >= 2 management-reachability losses + >= 2 D10
    intent violations — not a single 1-bit key.

(Management addressing uses the RFC 1918 block 172.16.0.0/16 — a clearly-private
"management VRF" style range — kept unambiguously distinct from the RFC 5737
documentation blocks used for the link nets (192.0.2.0/24, TEST-NET-1) and the
customer space (203.0.113.0/24, TEST-NET-3). All three RFC 5737 blocks are already
in use across the suite, so a clean RFC 1918 management block is used here.)

Verified ground truth is computed live by scripts/run_extended_scenario.py
--scenario mgmt_lockout (Batfish on 127.0.0.1:9997). DO NOT edit the config text
without re-verifying in Batfish — ground truth depends on it. Treat as frozen once
committed.
"""

from __future__ import annotations

NODES = ["jump", "core", "edge", "edge2"]

# Loopback (and BGP router-id) IP for each node.
LOOPBACK_IP = {
    "jump": "10.0.0.1",
    "core": "10.0.0.2",
    "edge": "10.0.0.3",
    "edge2": "10.0.0.4",
}

# The TWO managed devices' MANAGEMENT subnets + mgmt-IPs (each originated by its
# own device; NO static backup anywhere). These are the destinations of the
# jump-host -> device mgmt queries (D3) and the management-reachability intents (D10).
MGMT_PREFIXES = {"edge": "172.16.0.0/24", "edge2": "172.16.1.0/24"}
MGMT_IPS = {"edge": "172.16.0.1", "edge2": "172.16.1.1"}  # SSH/NETCONF endpoints

# The customer/data prefix (originated by edge; the NEGATIVE CONTROL — stays up).
CUSTOMER_PREFIX = "203.0.113.0/24"
CUSTOMER_IP = "203.0.113.1"

# The NOC jump-host's own subnet (its management source network).
JUMPHOST_SUBNET = "172.16.99.0/24"
JUMPHOST_IP = "172.16.99.1"

# Prefixes scored for the route diff (D2). We watch the CUSTOMER prefix + the four
# loopbacks: ALL of these survive the change, so D2 = ∅ is HONEST — every watched
# prefix is watched-and-correctly-NOT-lost, and a model that false-positives on any
# of them (e.g. claims the customer prefix or a loopback dropped) actually loses D2
# precision. The management prefixes are deliberately NOT in this set: their loss is
# the D3 reachability event + the D10 intent violation (the whole point of the
# class — a customer-prefix view is BLIND to it). They are NOT hidden from a watched
# set to fake the trap; they are simply scored on the dimensions where they fire.
WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "10.0.0.4/32", CUSTOMER_PREFIX,
]

# Physical links (lower node first), for the topology record / clab render.
LINKS = [
    ("jump", "eth1", "core", "eth1"),
    ("core", "eth2", "edge", "eth1"),
    ("core", "eth3", "edge2", "eth1"),
]

# The RR / aggregation router is the change target.
CHANGE_TARGET = "core"

_JUMP = """jump

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.1/32

auto eth1
iface eth1 inet static
    address 192.0.2.1/30

auto dum0
iface dum0 inet static
    address 172.16.99.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname jump
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
interface dum0
 ip address 172.16.99.1/24
!
ip route 10.0.0.2/32 192.0.2.2
ip route 10.0.0.3/32 192.0.2.2
ip route 10.0.0.4/32 192.0.2.2
!
router bgp 65000
 bgp router-id 10.0.0.1
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
  neighbor 10.0.0.2 next-hop-self
 exit-address-family
!
line vty
!
"""

_CORE = """core

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.2/32

auto eth1
iface eth1 inet static
    address 192.0.2.2/30

auto eth2
iface eth2 inet static
    address 192.0.2.5/30

auto eth3
iface eth3 inet static
    address 192.0.2.9/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname core
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
 ip address 192.0.2.5/30
!
interface eth3
 ip address 192.0.2.9/30
!
ip route 10.0.0.1/32 192.0.2.1
ip route 10.0.0.3/32 192.0.2.6
ip route 10.0.0.4/32 192.0.2.10
!
router bgp 65000
 bgp router-id 10.0.0.2
 neighbor 10.0.0.1 remote-as 65000
 neighbor 10.0.0.1 update-source lo
 neighbor 10.0.0.3 remote-as 65000
 neighbor 10.0.0.3 update-source lo
 neighbor 10.0.0.4 remote-as 65000
 neighbor 10.0.0.4 update-source lo
 !
 address-family ipv4 unicast
  neighbor 10.0.0.1 route-reflector-client
  neighbor 10.0.0.1 next-hop-self
  neighbor 10.0.0.3 route-reflector-client
  neighbor 10.0.0.3 next-hop-self
  neighbor 10.0.0.4 route-reflector-client
  neighbor 10.0.0.4 next-hop-self
 exit-address-family
!
line vty
!
"""

_EDGE = """edge

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto dum0
iface dum0 inet static
    address 203.0.113.1/24

auto dum1
iface dum1 inet static
    address 172.16.0.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname edge
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
 ip address 203.0.113.1/24
!
interface dum1
 ip address 172.16.0.1/24
!
ip route 10.0.0.1/32 192.0.2.5
ip route 10.0.0.2/32 192.0.2.5
ip route 10.0.0.4/32 192.0.2.5
!
router bgp 65000
 bgp router-id 10.0.0.3
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
  network 203.0.113.0/24
  network 172.16.0.0/24
  neighbor 10.0.0.2 next-hop-self
 exit-address-family
!
line vty
!
"""

_EDGE2 = """edge2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.4/32

auto eth1
iface eth1 inet static
    address 192.0.2.10/30

auto dum1
iface dum1 inet static
    address 172.16.1.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname edge2
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
interface dum1
 ip address 172.16.1.1/24
!
ip route 10.0.0.1/32 192.0.2.9
ip route 10.0.0.2/32 192.0.2.9
ip route 10.0.0.3/32 192.0.2.9
!
router bgp 65000
 bgp router-id 10.0.0.4
 neighbor 10.0.0.2 remote-as 65000
 neighbor 10.0.0.2 update-source lo
 !
 address-family ipv4 unicast
  network 172.16.1.0/24
  neighbor 10.0.0.2 next-hop-self
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified mgmt_lockout baseline)."""
    return {"jump": _JUMP, "core": _CORE, "edge": _EDGE, "edge2": _EDGE2}
