"""The `scale_deagg` baseline: a 2-AS eBGP pair for the D8 scale/overflow class.

This is the de-aggregation / table-flood baseline that grounds NetHELM **Class 8
(scale / resource overflow)** — the Rogers Jul-2022 mechanism re-cast as a clean,
Batfish-static experiment: a filter/summary removal multiplies the routes a
downstream device must install past its resource budget.

Topology (an eBGP pair; AS per node)::

    upstream (AS65010) ===== edge (AS65020)
      originates a block      installs what upstream sends; has a MODEST FIB budget
      (baseline: 1 SUMMARY    (baseline: under budget; post-change de-agg: over)
       100.64.0.0/16)

The whole point is that the BASELINE summarizes the block as a SINGLE aggregate
``100.64.0.0/16``, so the edge installs only a handful of routes (well under its
FIB budget). The de-aggregation change (scenario_scale_deagg) replaces that
summary with many more-specific /24s, flooding the edge past its budget.

Deterministic addressing (docs/authoring_topologies_and_scenarios.md §1):
  * node X      -> loopback 10.0.0.N/32 -> bgp router-id 10.0.0.N
        upstream=10.0.0.1, edge=10.0.0.2
  * the eBGP session rides the DIRECTLY-CONNECTED /30 link IPs (no update-source,
    no multihop — the simplest deterministic eBGP):
        upstream<->edge  192.0.2.0/30  (upstream=.1, edge=.2)
  * distinct ASNs 65010/65020 (RFC 6996 private range).

Prefix doctrine:
  * The customer block is 100.64.0.0/16 (RFC 6598 shared CGN space — a safe,
    documentation-grade block). Upstream sources it from a discard (blackhole)
    static so the aggregate is always up regardless of any real downstream path.
  * In the baseline upstream originates ONLY the /16 summary (one `network`).
  * Loopbacks 10.0.0.{1,2}/32 — each node originates its own (negative controls).

The edge's FIB budget is an annotation on the Scenario (resource_limits), NOT in
this config — Batfish gives the installed-route COUNT, the limit is a spec. The
budget is chosen so the baseline count is comfortably UNDER it and the post-change
(de-aggregated) count is OVER it. See ``scenario_scale_deagg`` for the budget.

Determinism: a chain of two nodes with a single origin per prefix and no ECMP tie;
router-ids pinned to loopbacks; the discard static keeps the summary up regardless
of timing. The route COUNT on a pinned snapshot is independent of any per-flow
hash, so it is byte-identical across runs. STATIC-DETERMINISTIC per
docs/oracle_determinism_spec_v1.md (the scale class scores count-vs-limit, never
which route a TCAM evicts).

Batfish-parseable FRR (CUMULUS_CONCATENATED, frr version 10.6.1), matching the
exact text format of the other baselines. Treat this file as frozen once verified.
"""

from __future__ import annotations

NODES = ["upstream", "edge"]

LOOPBACK_IP = {"upstream": "10.0.0.1", "edge": "10.0.0.2"}

ASN = {"upstream": 65010, "edge": 65020}

# The customer block upstream originates (RFC 6598 CGN documentation space).
BLOCK_PREFIX = "100.64.0.0/16"

# The number of more-specific /24s the de-aggregation change leaks (0..N-1).
# 100.64.0.0/24 .. 100.64.(DEAGG_COUNT-1).0/24. Chosen large enough that the
# post-change edge route count unambiguously crosses a modest FIB budget.
DEAGG_COUNT = 24

# D2 watch set: the loopbacks, the /16 summary, AND the constituent /24s. The
# de-aggregation REPLACES the /16 with its constituent /24s, so the /16 row truly
# leaves the edge's RIB while the /24s are ADDED. D2 honesty (red-team fix): we
# WATCH the /16 so D2 reflects reality — a model that correctly reports "the
# 100.64.0.0/16 supernet was withdrawn from the edge" is right, not penalised. So
# D2 prefixes_lost = {(edge, 100.64.0.0/16)} post-change. The /24s are also watched
# (they are ADDED, never lost, so they stay out of D2) and so are the loopbacks
# (negative controls). The thesis is NOT "no loss signal" (the /16 IS a real loss
# row) but "the only loss signal is a benign supernet->specifics SWAP — D3
# reachability is ∅ because the /24s cover the same space — while the REAL blast is
# the D8 FIB overflow that no loss/connectivity view captures." That is the
# scale-class trap, stated honestly.
WATCHED_PREFIXES = [
    "10.0.0.1/32", "10.0.0.2/32", BLOCK_PREFIX,
] + [f"100.64.{i}.0/24" for i in range(DEAGG_COUNT)]

# Physical links (for the topology record / future containerlab rendering).
LINKS = [
    ("upstream", "eth1", "edge", "eth1"),
]

CHANGE_TARGET = "upstream"


_UPSTREAM = """upstream

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.1/32

auto eth1
iface eth1 inet static
    address 192.0.2.1/30

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname upstream
service integrated-vtysh-config
!
ip forwarding
!
ip route 100.64.0.0/16 blackhole
!
interface lo
 ip address 10.0.0.1/32
!
interface eth1
 ip address 192.0.2.1/30
!
router bgp 65010
 bgp router-id 10.0.0.1
 neighbor 192.0.2.2 remote-as 65020
 !
 address-family ipv4 unicast
  network 10.0.0.1/32
  network 100.64.0.0/16
 exit-address-family
!
line vty
!
"""


_EDGE = """edge

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
hostname edge
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
router bgp 65020
 bgp router-id 10.0.0.2
 neighbor 192.0.2.1 remote-as 65010
 !
 address-family ipv4 unicast
  network 10.0.0.2/32
 exit-address-family
!
line vty
!
"""


def baseline_configs() -> dict[str, str]:
    """Return a fresh {node: config_text} mapping (verified scale_deagg baseline)."""
    return {"upstream": _UPSTREAM, "edge": _EDGE}
