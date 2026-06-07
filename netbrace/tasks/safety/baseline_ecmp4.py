"""The `ecmp4` baseline: a 4-node topology with two equal-cost paths (D5 scenario).

Scenario S06/S14-flavored (paper/refs/blast_radius_scenario_catalog.md). `src`
reaches `dst`'s service prefix (10.0.0.4/32) over TWO equal-cost static paths,
via `m1` and via `m2`. The change removes one of the two paths on `src`: the
destination is still fully reachable (D3 sees nothing), no session/prefix is lost
(D1/D2 see nothing) — only the *redundancy* drops from 2 paths to 1 (D5).

        eth1 ---- m1 ---- eth2
   src                         dst
        eth2 ---- m2 ---- eth2

Addressing follows docs/authoring_topologies_and_scenarios.md.
Verified: Batfish shows 2 next-hops for 10.0.0.4/32 on src pre-change, 1 post.
"""

from __future__ import annotations

import difflib

from netbrace.topology.patches import apply_unified_diff

NODES = ["src", "m1", "m2", "dst"]
LOOPBACK_IP = {"src": "10.0.0.1", "m1": "10.0.0.2", "m2": "10.0.0.3", "dst": "10.0.0.4"}
WATCHED_PREFIXES = ["10.0.0.4/32"]
LINKS = [
    ("src", "eth1", "m1", "eth1"),
    ("src", "eth2", "m2", "eth1"),
    ("m1", "eth2", "dst", "eth1"),
    ("m2", "eth2", "dst", "eth2"),
]

CHANGE_TARGET = "src"
# (node, dst_prefix) pairs to check for a drop in installed path count.
REDUNDANCY_TARGETS = [("src", "10.0.0.4/32")]
# The ECMP next-hop removed by the change (the m2 path).
_REMOVED_LINE = "ip route 10.0.0.4/32 192.0.2.6"


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
ip route 10.0.0.4/32 192.0.2.2
ip route 10.0.0.4/32 192.0.2.6
!
line vty
!
"""

_M1 = """m1

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
hostname m1
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

_M2 = """m2

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
hostname m2
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
    """Return a fresh {node: config_text} mapping (verified ecmp4 baseline)."""
    return {"src": _SRC, "m1": _M1, "m2": _M2, "dst": _DST}


def _post_src_config() -> str:
    """src with one of the two ECMP routes to 10.0.0.4/32 removed."""
    after = "\n".join(ln for ln in _SRC.splitlines() if ln.strip() != _REMOVED_LINE)
    return after + "\n" if _SRC.endswith("\n") else after


def change_patch() -> str:
    """Unified diff on src removing one ECMP next-hop. Guaranteed to apply."""
    before, after = _SRC, _post_src_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="src.conf", tofile="src.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("ecmp4 change patch does not round-trip")
    return patch
