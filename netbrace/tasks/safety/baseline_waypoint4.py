"""The `waypoint4` baseline: a 4-node static-routed topology for the D4 scenario.

Purpose (scenario S18 in paper/refs/blast_radius_scenario_catalog.md): demonstrate
a blast radius that the v0 dimensions (sessions/prefixes/reachability) CANNOT see.

Topology (two disjoint paths from src to dst):

        eth1        eth2
   src -------- way -------- dst       (the "good" path, transits the waypoint)
    |                         |
    +---------- alt ----------+        (the bypass path)
        eth2        eth2

Baseline: src reaches dst's loopback (10.0.0.4/32) via `way` — an intentional
steering, e.g. an inspection/IDS node that all src->dst traffic MUST transit.
The change rewrites one static route on src so traffic takes the `alt` path,
BYPASSING `way`. dst is still fully reachable (D3 sees nothing), no session or
prefix is lost (D1/D2 see nothing) — only the D4 waypoint intent is violated.

Addressing follows docs/authoring_topologies_and_scenarios.md:
  loopbacks 10.0.0.{1..4}/32; p2p links from 192.0.2.0/24 in /30s.

Verified to parse in Batfish and to route src->dst through `way` (GATE 1).
"""

from __future__ import annotations

import difflib

from netbrace.topology.patches import apply_unified_diff

NODES = ["src", "way", "alt", "dst"]

LOOPBACK_IP = {"src": "10.0.0.1", "way": "10.0.0.2", "alt": "10.0.0.3", "dst": "10.0.0.4"}

WATCHED_PREFIXES = ["10.0.0.4/32"]  # the destination service prefix

# (a_node, a_intf, b_node, b_intf)
LINKS = [
    ("src", "eth1", "way", "eth1"),
    ("src", "eth2", "alt", "eth1"),
    ("way", "eth2", "dst", "eth1"),
    ("alt", "eth2", "dst", "eth2"),
]

# The intent the change violates: traffic from `src` to 10.0.0.4/32 MUST transit `way`.
WAYPOINT_INTENTS = [("src", "10.0.0.4/32", "way")]

CHANGE_TARGET = "src"


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
ip route 10.0.0.4/32 192.0.2.2
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
ip route 10.0.0.4/32 192.0.2.10
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
ip route 10.0.0.4/32 192.0.2.14
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
ip route 10.0.0.1/32 192.0.2.9
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified waypoint4 baseline)."""
    return {"src": _SRC, "way": _WAY, "alt": _ALT, "dst": _DST}


def _post_src_config() -> str:
    """src with the dst route rerouted from `way` (.2) to `alt` (.6) — the bypass."""
    return _SRC.replace(
        "ip route 10.0.0.4/32 192.0.2.2",
        "ip route 10.0.0.4/32 192.0.2.6",
    )


def change_patch() -> str:
    """Unified diff on src that moves the dst route off the waypoint path.

    Built with difflib so it is guaranteed to apply via apply_unified_diff
    (same convention as tasks/safety/generator.py)."""
    before, after = _SRC, _post_src_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="src.conf", tofile="src.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    # Self-check: the patch must reproduce `after` exactly.
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("waypoint4 change patch does not round-trip")
    return patch
