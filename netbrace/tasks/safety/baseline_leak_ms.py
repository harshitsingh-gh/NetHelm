"""The `leak_ms` baseline: a 3-AS eBGP chain for the more-specific route-leak class.

This is the FIRST multi-AS (eBGP) baseline in the safety suite — every prior one
is single-AS iBGP. It exists to demonstrate the Class-2 thesis: a change where the
naive blast signals give NOTHING (D1 sessions_lost = ∅ AND D2 prefixes_lost = ∅,
the change even ADDS a route) yet there is a REAL data-plane blast (a blackhole on
traffic toward the victim space). That is the "session-count and prefix-count give
no signal" property of the Telekom-Malaysia-2015 and Cloudflare-2019 route leaks.

Topology (an eBGP chain; AS per node)::

    victim (AS65001) ===== transit (AS65002) ===== leaker (AS65003)
      originates                observer                 (post-change: leaks a
      203.0.113.0/24            (in the middle)           more-specific /25)

Deterministic addressing (docs/authoring_topologies_and_scenarios.md §1):
  * node X      -> loopback 10.0.0.N/32 -> bgp router-id 10.0.0.N
        victim=10.0.0.1, transit=10.0.0.2, leaker=10.0.0.3
  * eBGP sessions ride the DIRECTLY-CONNECTED /30 link IPs (not loopbacks): no
    update-source, no multihop — the simplest deterministic eBGP. Link order:
        victim<->transit  192.0.2.0/30  (victim=.1, transit=.2)
        transit<->leaker  192.0.2.4/30  (transit=.5, leaker=.6)
  * distinct ASNs 65001/65002/65003 (RFC 6996 private range).

Prefix doctrine (what makes the trap clean):
  * Victim 203.0.113.0/24 -- the protected customer prefix. Originated ONLY by the
    victim (on dummy dum0 = 203.0.113.1/24, a real connected host route). Pre-state:
    transit AND leaker reach 203.0.113.1 via the victim. No more-specific exists, so
    the /24 is strictly preferred everywhere -- NO equal-cost / tie ambiguity.
  * Leaker's own legit prefix 198.51.100.0/24 (dummy dum0 = 198.51.100.1/24) -- a
    negative control: a normal prefix the leaker really serves, unaffected by the
    change.
  * Loopbacks 10.0.0.{1,2,3}/32 -- each node originates its own with `network`; they
    are negative controls for D1/D2.

Pre-state reachability (the "looks fine" steady state), to be confirmed by the
oracle: transit -> 203.0.113.1 is DELIVERED via victim; transit -> 198.51.100.1 is
DELIVERED via leaker; all eBGP sessions ESTABLISHED.

Strict-preference guarantee: in the baseline there is exactly one origin for each
prefix and a single path at the observer (a chain, not a mesh), so no equal-cost
ECMP tie can perturb the chosen path. Router-ids are pinned to the loopbacks. This
is STATIC-DETERMINISTIC per docs/oracle_determinism_spec_v1.md (class 2 row).

Batfish-parseable FRR (CUMULUS_CONCATENATED, frr version 10.6.1), matching the
exact text format of the other baselines. Treat this file as frozen once verified.
"""

from __future__ import annotations

NODES = ["victim", "transit", "leaker"]

LOOPBACK_IP = {"victim": "10.0.0.1", "transit": "10.0.0.2", "leaker": "10.0.0.3"}

ASN = {"victim": 65001, "transit": 65002, "leaker": 65003}

# The protected victim customer prefix (and a host inside it to probe).
VICTIM_PREFIX = "203.0.113.0/24"
VICTIM_IP = "203.0.113.1"

# The more-specific the leaker originates POST-change (covers VICTIM_IP).
LEAK_PREFIX = "203.0.113.0/25"

# The leaker's own legitimately-served prefix (negative control).
LEAKER_PREFIX = "198.51.100.0/24"
LEAKER_IP = "198.51.100.1"

# D2 watch set: the victim /24, the leaker /24, all loopbacks, AND the leaked /25.
# The /25 is watched so a model that (correctly) reports it as an *added* route is
# not penalised, and so we can assert the legit /24 is NOT lost from any RIB.
WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32",
    VICTIM_PREFIX, LEAKER_PREFIX, LEAK_PREFIX,
]

# Physical links (for the topology record / future containerlab rendering).
LINKS = [
    ("victim", "eth1", "transit", "eth1"),
    ("transit", "eth2", "leaker", "eth1"),
]

CHANGE_TARGET = "leaker"


_VICTIM = """victim

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.1/32

auto eth1
iface eth1 inet static
    address 192.0.2.1/30

auto dum0
iface dum0 inet static
    address 203.0.113.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname victim
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
 ip address 203.0.113.1/24
!
router bgp 65001
 bgp router-id 10.0.0.1
 neighbor 192.0.2.2 remote-as 65002
 !
 address-family ipv4 unicast
  network 10.0.0.1/32
  network 203.0.113.0/24
 exit-address-family
!
line vty
!
"""


_TRANSIT = """transit

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

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname transit
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
router bgp 65002
 bgp router-id 10.0.0.2
 neighbor 192.0.2.1 remote-as 65001
 neighbor 192.0.2.6 remote-as 65003
 !
 address-family ipv4 unicast
  network 10.0.0.2/32
  neighbor 192.0.2.1 route-map ALLOW_VICTIM_IN in
 exit-address-family
!
route-map ALLOW_VICTIM_IN permit 10
!
line vty
!
"""


_LEAKER = """leaker

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.3/32

auto eth1
iface eth1 inet static
    address 192.0.2.6/30

auto dum0
iface dum0 inet static
    address 198.51.100.1/24

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname leaker
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
 ip address 198.51.100.1/24
!
router bgp 65003
 bgp router-id 10.0.0.3
 neighbor 192.0.2.5 remote-as 65002
 !
 address-family ipv4 unicast
  network 10.0.0.3/32
  network 198.51.100.0/24
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified leak_ms baseline)."""
    return {"victim": _VICTIM, "transit": _TRANSIT, "leaker": _LEAKER}
