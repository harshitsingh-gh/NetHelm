"""The `clos_summary` baseline: a 2-spine / 3-leaf Clos eBGP underlay (RFC 7938).

This is the DC-fabric baseline for the route-summarization blackhole class. RFC 7938
warns summarization in a Clos causes black-holing (§3.2.2 one-path-per-Tier-1
property; §5.2.3). NOTE: §5.2.3's canonical trigger is a *link failure* on a healthy
symmetric fabric; this baseline instead bakes a **fixed asymmetry** (no spine2↔leaf3
link) that the summary masks — a *fixed-asymmetry instance* of the hazard, not the
dynamic link-failure case. The §5.2.3 link-failure version is the queued upgrade.
It is a per-device-ASN eBGP underlay, the RFC-7938 canonical scheme, NOT iBGP.

Topology (a partial Clos — the asymmetry is DELIBERATE and FIXED in BOTH the pre
and the post snapshot):

        spine1 (AS65001)                 spine2 (AS65002)
        /     |      \\                    /      |
   leaf1     leaf2    leaf3           leaf1    leaf2     (NO spine2--leaf3 link)
  (65101)   (65102)  (65103)        (shared) (shared)

  * leaf3 (AS65103) ORIGINATES the server prefix 10.3.0.0/24 (host 10.3.0.1).
  * spine1 connects to all three leaves -> spine1 has a DIRECT path to 10.3.0.0/24.
  * spine2 connects to leaf1 and leaf2 only -> spine2 has NO DIRECT link to leaf3.
    Models the RFC-7938 "exactly one Tier-1 path per server" property degraded by
    one missing/failed uplink, held FIXED so the delta is purely the summarization
    config (a clean 2-snapshot Batfish-static diff, not a topology change).
    VERIFIED-ON-LIVE-BATFISH (do not mis-state): in the BASELINE spine2 DOES learn
    10.3.0.0/24 — but only INDIRECTLY, via leaf1/leaf2 re-advertising it back up
    (a valley path); spine2 has no DIRECT path. That indirect path is exactly what
    the post-change summarization severs.
  * leaf1 and leaf2 each peer with BOTH spines -> they are ECMP-capable remote
    sources toward the server prefix.

Deterministic addressing (docs/authoring_topologies_and_scenarios.md §1):
  * Loopbacks / router-ids live OUTSIDE the 10.0.0.0/8 server space, in
    172.16.0.0/16, so the summary the post-change introduces can never cover a
    router-id (keeps the D2 watch set unambiguous):
        spine1=172.16.0.1  spine2=172.16.0.2
        leaf1 =172.16.1.1  leaf2 =172.16.1.2  leaf3=172.16.1.3
  * eBGP sessions ride the directly-connected /30 link IPs (no multihop, no
    update-source) — the simplest deterministic eBGP, matching leak_ms.
        spine1<->leaf1  192.0.2.0/30   (spine1=.1,  leaf1=.2)
        spine1<->leaf2  192.0.2.4/30   (spine1=.5,  leaf2=.6)
        spine1<->leaf3  192.0.2.8/30   (spine1=.9,  leaf3=.10)
        spine2<->leaf1  192.0.2.12/30  (spine2=.13, leaf1=.14)
        spine2<->leaf2  192.0.2.16/30  (spine2=.17, leaf2=.18)
  * per-device ASNs in the RFC 6996 private range (RFC 7938 §5.2.1 scheme):
        spine1=65001 spine2=65002 leaf1=65101 leaf2=65102 leaf3=65103
  * `bgp bestpath as-path multipath-relax` + `maximum-paths 2` on the leaves so
    equal paths arriving with DIFFERENT AS_PATHs (spine1 vs spine2) qualify as
    multipath (RFC 7938 §6.2). This is what makes the post-change blackhole an
    ECMP *fraction*, not total loss.

Server prefix doctrine (what makes the trap clean):
  * 10.3.0.0/24 originated ONLY by leaf3 (connected host 10.3.0.1 on dum0). In the
    BASELINE the spines advertise the SPECIFIC /24 to the leaves, so:
        - leaf3->spine1 propagates 10.3.0.0/24 to leaf1, leaf2. leaf1/leaf2 prefer
          this DIRECT spine1 path; they also re-advertise the /24 up to spine2, so
          spine2 learns it indirectly (the loop-prevented copy is never best at the
          leaves). DELIVERED via spine1, no ECMP yet on the specific.
    There is NO covering summary anywhere in the baseline, so LPM is unambiguous
    and the chosen path is unique -> STATIC-DETERMINISTIC.

Pre-state reachability (the "looks fine" steady state, to be confirmed by the
oracle): leaf1->10.3.0.1 DELIVERED via spine1; leaf2->10.3.0.1 DELIVERED via
spine1; all five eBGP sessions ESTABLISHED. spine2 has an indirect (valley) route
to the server space via the leaves but is not on the leaves' best path, so no
traffic is drawn to it yet — until summarization severs that indirect path.

STATIC-DETERMINISTIC per docs/oracle_determinism_spec_v1.md: scored as the
data-plane SET via traceroute disposition (a blackhole trace EXISTS), never the
per-flow ECMP hash / chosen path. Router-ids pinned to loopbacks. Treat this file
as frozen once verified.

Grounding: RFC 7938 §5.2.3 (verbatim warning), §3.2.2 (one-path property);
knowledge/corpus/dc/dc_summarization_ecmp_pitfalls.md Part A; ipSpace "Avoid
summarization in leaf-and-spine."
"""

from __future__ import annotations

NODES = ["spine1", "spine2", "leaf1", "leaf2", "leaf3"]

LOOPBACK_IP = {
    "spine1": "172.16.0.1", "spine2": "172.16.0.2",
    "leaf1": "172.16.1.1", "leaf2": "172.16.1.2", "leaf3": "172.16.1.3",
}

ASN = {
    "spine1": 65001, "spine2": 65002,
    "leaf1": 65101, "leaf2": 65102, "leaf3": 65103,
}

# The server prefix originated by leaf3, and a real host inside it to probe.
SERVER_PREFIX = "10.3.0.0/24"
SERVER_IP = "10.3.0.1"

# The covering summary the POST change introduces on the spines (a /8 over the
# whole 10.0.0.0/8 server space). Watched so an "added route" report is not
# penalised and so the oracle can confirm the specific's fate.
SUMMARY_PREFIX = "10.0.0.0/8"

# D2 watch set: the server /24, the summary /8, all loopbacks.
WATCHED_PREFIXES = [
    "172.16.0.1/32", "172.16.0.2/32",
    "172.16.1.1/32", "172.16.1.2/32", "172.16.1.3/32",
    SERVER_PREFIX, SUMMARY_PREFIX,
]

# Physical links (for the topology record / future containerlab rendering).
LINKS = [
    ("spine1", "eth1", "leaf1", "eth1"),
    ("spine1", "eth2", "leaf2", "eth1"),
    ("spine1", "eth3", "leaf3", "eth1"),
    ("spine2", "eth1", "leaf1", "eth2"),
    ("spine2", "eth2", "leaf2", "eth2"),
    # NOTE: no spine2<->leaf3 link — the fixed asymmetry.
]

# The post change is applied to BOTH spines (a fabric-wide template), but a
# Scenario patches a single target; we patch spine2 (the spine that blackholes)
# and have the helper also emit spine1's summary so both originate it. See
# scenario_clos_summary.py for how both spines are summarized.
CHANGE_TARGET = "spine2"


_SPINE1 = """spine1

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 172.16.0.1/32

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
hostname spine1
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 172.16.0.1/32
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
router bgp 65001
 bgp router-id 172.16.0.1
 bgp bestpath as-path multipath-relax
 neighbor 192.0.2.2 remote-as 65101
 neighbor 192.0.2.6 remote-as 65102
 neighbor 192.0.2.10 remote-as 65103
 !
 address-family ipv4 unicast
  network 172.16.0.1/32
  maximum-paths 2
 exit-address-family
!
line vty
!
"""


_SPINE2 = """spine2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 172.16.0.2/32

auto eth1
iface eth1 inet static
    address 192.0.2.13/30

auto eth2
iface eth2 inet static
    address 192.0.2.17/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname spine2
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 172.16.0.2/32
!
interface eth1
 ip address 192.0.2.13/30
!
interface eth2
 ip address 192.0.2.17/30
!
router bgp 65002
 bgp router-id 172.16.0.2
 bgp bestpath as-path multipath-relax
 neighbor 192.0.2.14 remote-as 65101
 neighbor 192.0.2.18 remote-as 65102
 !
 address-family ipv4 unicast
  network 172.16.0.2/32
  maximum-paths 2
 exit-address-family
!
line vty
!
"""


_LEAF1 = """leaf1

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 172.16.1.1/32

auto eth1
iface eth1 inet static
    address 192.0.2.2/30

auto eth2
iface eth2 inet static
    address 192.0.2.14/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname leaf1
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 172.16.1.1/32
!
interface eth1
 ip address 192.0.2.2/30
!
interface eth2
 ip address 192.0.2.14/30
!
router bgp 65101
 bgp router-id 172.16.1.1
 bgp bestpath as-path multipath-relax
 neighbor 192.0.2.1 remote-as 65001
 neighbor 192.0.2.13 remote-as 65002
 !
 address-family ipv4 unicast
  network 172.16.1.1/32
  maximum-paths 2
 exit-address-family
!
line vty
!
"""


_LEAF2 = """leaf2

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 172.16.1.2/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto eth2
iface eth2 inet static
    address 192.0.2.18/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname leaf2
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 172.16.1.2/32
!
interface eth1
 ip address 192.0.2.6/30
!
interface eth2
 ip address 192.0.2.18/30
!
router bgp 65102
 bgp router-id 172.16.1.2
 bgp bestpath as-path multipath-relax
 neighbor 192.0.2.5 remote-as 65001
 neighbor 192.0.2.17 remote-as 65002
 !
 address-family ipv4 unicast
  network 172.16.1.2/32
  maximum-paths 2
 exit-address-family
!
line vty
!
"""


_LEAF3 = """leaf3

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 172.16.1.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.10/30

auto dum0
iface dum0 inet static
    address 10.3.0.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname leaf3
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 172.16.1.3/32
!
interface eth1
 ip address 192.0.2.10/30
!
interface dum0
 ip address 10.3.0.1/24
!
router bgp 65103
 bgp router-id 172.16.1.3
 bgp bestpath as-path multipath-relax
 neighbor 192.0.2.9 remote-as 65001
 !
 address-family ipv4 unicast
  network 172.16.1.3/32
  network 10.3.0.0/24
  maximum-paths 2
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified clos_summary baseline)."""
    return {
        "spine1": _SPINE1, "spine2": _SPINE2,
        "leaf1": _LEAF1, "leaf2": _LEAF2, "leaf3": _LEAF3,
    }
