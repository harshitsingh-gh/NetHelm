"""The `ipc3` baseline: a 3-node iBGP route-reflector spine, AS 65000.

This is the verified baseline for **Class 1 — Internal routing-policy silent
withdrawal** (the "implicit deny-all" maintenance trap; operational lore /
Maintenance Type 2 — NOT the Rogers Jul-2022 mechanism, which was a filter removal →
route flood → overload). It is intentionally NOT the
`square4` full mesh: square4 gives every loopback a static backup, which would
*mask* a routing-policy withdrawal (the static route keeps the FIB populated and
reachability alive — see `scenario_blackhole.py`). Class 1 needs a prefix whose
reachability depends on BGP ALONE, so a withdrawal actually collapses the data
plane while sessions stay ESTABLISHED.

Topology (a line; r1 is the route reflector, r2/r3 are clients)::

      r2 ───── r1 ───── r3
    (client)  (RR)    (client, origin)

Deterministic addressing (per docs/authoring_topologies_and_scenarios.md §1):
  * node rX  → loopback 10.0.0.X/32 → bgp router-id 10.0.0.X
  * link r1–r2 = 192.0.2.0/30 (r1=.1, r2=.2); link r1–r3 = 192.0.2.4/30 (r1=.5, r3=.6)
  * iBGP: r2 and r3 are route-reflector-clients of r1 (next-hop-self toward both).
    r2 and r3 do NOT peer with each other — r1 is the sole transit between them.

Two prefix CLASSES, deliberately distinct:
  * **Loopbacks** 10.0.0.{1,2,3}/32 — every node has a STATIC route to each other
    loopback (far-side IP of the direct link, via r1 for the r2↔r3 pair). Loopback
    reachability is therefore BGP-INDEPENDENT (the same doctrine as square4). This
    keeps the iBGP sessions up and is what makes the trap convincing: loopbacks
    survive, so the network "looks fine."
  * **Customer prefix** 203.0.113.0/24 — originated by r3 (`network` statement on a
    dummy interface), with **NO static route to it anywhere**. Its reachability
    depends ENTIRELY on the BGP advertisement r3 → r1 → r2. This is the prefix the
    Class-1 filter withdraws.

Verified on live Batfish (batfish/allinone, 127.0.0.1:9997), 2026-06-08:
  * format CUMULUS_CONCATENATED (FRR), all 3 configs PASSED parse.
  * 4 directional iBGP sessions, all ESTABLISHED.
  * r2 FIB has 203.0.113.0/24 via ibgp (next-hop 10.0.0.3); r1, r3 reach it.
DO NOT edit the config text without re-verifying in Batfish — ground truth depends
on it. Treat this file as frozen once committed.
"""

from __future__ import annotations

NODES = ["r1", "r2", "r3"]

# Loopback (and BGP router-id) IP for each node.
LOOPBACK_IP = {"r1": "10.0.0.1", "r2": "10.0.0.2", "r3": "10.0.0.3"}

# The customer/transit prefix r3 originates (NO static backup anywhere).
CUSTOMER_PREFIX = "203.0.113.0/24"
CUSTOMER_IP = "203.0.113.1"  # an address inside it, for traceroute

# Prefixes scored for the route diff (D2). The loopbacks survive (static backup);
# the customer prefix is the one that is actually withdrawn — include all four so
# the grader can confirm the loopbacks are NOT collateral damage.
WATCHED_PREFIXES = ["10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "203.0.113.0/24"]

# Physical links (lower node number first), for the topology record / clab render.
LINKS = [
    ("r1", "eth1", "r2", "eth1"),
    ("r1", "eth2", "r3", "eth1"),
]

# The RR (r1) is the change target for S-IPC-01.
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
    address 203.0.113.1/24

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
 ip address 203.0.113.1/24
!
ip route 10.0.0.1/32 192.0.2.5
ip route 10.0.0.2/32 192.0.2.5
!
router bgp 65000
 bgp router-id 10.0.0.3
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
    """Return a fresh {node: config_text} mapping (verified ipc3 baseline)."""
    return {"r1": _R1, "r2": _R2, "r3": _R3}


# --------------------------------------------------------------------------- #
# has-static SIBLING (Class-1 discriminator / "trap that looks like the collapse
# but isn't"). Identical to the baseline EXCEPT r2 has a STATIC backup to the
# customer prefix (via r1's near-side link IP 192.0.2.1). The same outbound
# CLEANUP filter still withdraws 203.0.113.0/24 from r2's BGP RIB, so the
# control-plane withdrawal (D9) still fires — but the static keeps r2's FIB
# populated (D2 silent) and reachability alive (D3 silent). This makes the
# sibling DISTINGUISHABLE from a no-op (which yields an empty D9 set).
#
# Live-verified on batfish/allinone (2026-06-08, both snapshots PASSED parse):
#   * pre/post bgp BEST loss = {(r2, default, 203.0.113.0/24)}  (D9 fires)
#   * r2 customer prefix in FIB pre AND post  (via static 192.0.2.1)  (D2 silent)
#   * r2 -> 203.0.113.1 traceroute ACCEPTED pre AND post  (D3 silent)
# The static (admin distance 1) wins over iBGP (200) in BOTH snapshots, so the
# installed next-hop is identical pre/post — deterministic by construction.

# Anchor on r2 after its existing loopback statics (frozen baseline text).
_R2_STATIC_ANCHOR = "ip route 10.0.0.3/32 192.0.2.1\n"
_R2_CUSTOMER_STATIC = f"ip route {CUSTOMER_PREFIX} 192.0.2.1\n"


def baseline_configs_static() -> dict[str, str]:
    """ipc3 baseline with a STATIC backup to the customer prefix on r2.

    The has-static sibling for the Class-1 discriminator. Same r1/r3 as the
    frozen baseline; r2 gains exactly one static route.
    """
    cfgs = baseline_configs()
    r2 = cfgs["r2"]
    if _R2_STATIC_ANCHOR not in r2:
        raise RuntimeError("ipc3 baseline r2 changed; re-verify static-sibling anchor")
    cfgs["r2"] = r2.replace(_R2_STATIC_ANCHOR, _R2_STATIC_ANCHOR + _R2_CUSTOMER_STATIC, 1)
    return cfgs
