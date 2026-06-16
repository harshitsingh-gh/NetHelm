# IS-IS (Intermediate System to Intermediate System) — Protocol Reference

## Overview
IS-IS is a link-state IGP (Interior Gateway Protocol) defined in ISO 10589 and extended for IP by RFC 1195. Unlike OSPF, IS-IS runs directly over L2 (not IP — protocol ID 0xFEFE on Ethernet) and is widely used in service provider cores. It is the dominant IGP in large-scale ISP and DC backbone networks because of its stability, scalability, and protocol-independent architecture (it can carry both IPv4 and IPv6 TLVs natively).

## IS-IS vs OSPF Key Differences
| Feature | IS-IS | OSPF |
|---|---|---|
| Transport | Directly over L2 (not IP) | IP protocol 89 |
| Area model | Level-1 / Level-2 (hierarchical) | Area 0 backbone + non-backbone areas |
| IPv6 support | Native via TLV (RFC 5308) | Separate OSPFv3 |
| Route types | L1 routes, L2 routes, inter-area (leaked) | Intra-area, inter-area, external |
| LSP vs LSA | LSPs (Link State PDUs) | LSAs (Link State Advertisements) |
| DR equivalent | DIS (Designated IS) — no BDR concept | DR + BDR |
| Authentication | Per-PDU TLV | Per-area or per-interface |
| Topology abstraction | Node-centric (TED-like) | Node-centric |

## IS-IS Levels
- **Level-1 (L1)**: intra-area routing only. L1 routers have a complete view of their area but only a default route pointing toward the nearest L1/L2 router for inter-area traffic.
- **Level-2 (L2)**: backbone routing between areas. L2 routers maintain a full L2 topology database spanning all areas.
- **L1/L2 router**: ABR equivalent — participates in both L1 and L2, leaks summary routes between levels.

**Critical difference from OSPF**: IS-IS area boundaries are on LINKS, not on routers. A router can have some interfaces in L1 and others in L2. All interfaces on a router that belongs to an area are in that area.

## IS-IS PDU Types
- **Hello (IIH — IS-IS Hello)**: neighbor discovery and adjacency maintenance. Sent per-interface.
  - LAN IIH: for broadcast segments (selects DIS)
  - P2P IIH: for point-to-point links
- **LSP (Link State PDU)**: topology advertisement — equivalent to OSPF LSA. Flooded within the level.
- **CSNP (Complete Sequence Number PDU)**: full database summary, used for synchronization (like DBD in OSPF)
- **PSNP (Partial Sequence Number PDU)**: requests specific LSPs (like LSR in OSPF)

## IS-IS Adjacency Formation
Neighbors form adjacency when:
- Hello PDUs received (IIH)
- Area address matches (for L1)
- System IDs must be unique
- Authentication matches (if configured)
- **MTU must match** — IS-IS hello PDUs carry MTU; mismatch = adjacency failure (same as OSPF EXSTART issue)
- Hold time negotiated: smaller of the two configured values

**Adjacency states**: Down → Init → Up

## DIS (Designated IS)
On multi-access (broadcast) segments, the DIS is elected (highest interface priority, then highest MAC address — no backup DIS like OSPF BDR).

**Key difference from OSPF**: DIS election is preemptive — if a higher-priority router appears, it immediately takes over (OSPF DR/BDR is non-preemptive). This causes transient disruption.

**Blast radius of DIS re-election**: 
- New DIS sends CSNP, others send LSPs to it
- Transient topology churn during re-election
- D7 (forwarding path changes) for paths through the broadcast segment

## IS-IS TLVs Relevant to Blast Radius
- TLV 2 (IS Neighbors): lists adjacencies; removing changes topology
- TLV 128/130 (IP Internal/External Reachability): IPv4 prefixes
- TLV 135 (Extended IP Reachability): IPv4 prefixes with TE metrics (RFC 5305)
- TLV 236 (IPv6 Reachability): IPv6 prefixes (RFC 5308)
- TLV 22 (Extended IS Reachability): adjacencies with TE metrics
- TLV 137 (Dynamic Hostname): router name
- Sub-TLV 3 (Administrative group/color): for TE constraints

## Wide vs Narrow Metrics
- **Narrow metric**: original IS-IS; max metric = 63 per link, 1023 total path
- **Wide metric (RFC 5305)**: 24-bit link metric, 32-bit path metric; required for MPLS TE
- FRR config: `metric-style wide` (required for SR and TE)

## IS-IS and BGP Interaction
Like OSPF, IS-IS provides the underlay for BGP next-hop resolution in service provider cores:
1. BGP peers use loopbacks as update-source
2. Loopback reachability comes from IS-IS
3. IS-IS adjacency failure → loopback unreachable → BGP next-hop fails → BGP prefixes withdrawn from FIB
4. This is the same recursive resolution chain as OSPF, but in IS-IS networks

## Blast Radius Patterns for IS-IS

### Pattern: IS-IS Adjacency Loss
- **Trigger**: link failure or `no isis enable` on an interface
- **D-dimensions**: D7 (forwarding path changes for affected paths), D3 (reachability lost for destinations only reachable via failed link), D2 (prefixes reachable only via failed link)
- **BGP cascade**: same as OSPF — BGP next-hops resolved via IS-IS lose their paths

### Pattern: L1/L2 Boundary Misconfiguration
- **Trigger**: L1/L2 router misconfigured as L1-only; inter-area routes no longer leaked
- **Effect**: L1 area loses reachability to all L2 destinations (only default route, and if that's missing, complete isolation)
- **D3**: complete isolation of the affected area
- **Subtle failure**: L1 routers in the area show adjacencies up, LSP database full — everything looks correct at the IS-IS level; only the missing L2 leaking is the bug

### Pattern: IS-IS Overload Bit
- **Trigger**: `set-overload-bit` configured (used during boot or maintenance)
- **Effect**: other routers avoid using this router for transit; only directly connected prefixes are reachable via it
- **D4/D7**: traffic that previously transited this router is rerouted
- **Use case**: graceful maintenance — set overload bit, wait for traffic to drain, then make config changes

### Pattern: IS-IS Authentication Mismatch
- **Trigger**: authentication key changed on one interface but not the peer
- **Effect**: adjacency drops; same cascade as link failure
- **Subtle**: authentication failure in IS-IS is logged at DEBUG level on some platforms; NOC may not see it in standard alarms

## IS-IS Metric Manipulation and Blast Radius
Setting `isis metric 16777214` (max wide metric) on a link effectively removes it from the topology (traffic stops using it unless it's the only path). This is a common maintenance technique.

**Blast radius**: D7 (traffic shifts away from the high-metric link), D4 (waypoint changes)

## FRR IS-IS Config
```
interface eth0
 ip router isis CORE
 isis metric 10
 isis circuit-type level-2-only
!
router isis CORE
 net 49.0001.0001.0001.0001.00
 is-type level-2-only
 metric-style wide
 log-adjacency-changes
```

## Batfish IS-IS Support
Batfish has limited IS-IS support compared to OSPF/BGP:
- Basic IS-IS adjacency modeling
- Route redistribution between IS-IS and BGP is partially supported
- TE extensions (sub-TLVs, SR extensions) are NOT modeled
- Verify specific features against pybatfish docs before using IS-IS for grading
