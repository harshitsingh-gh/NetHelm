# Network Topology Failure Chain Analysis for Blast Radius

## Overview
Blast radius is not just about individual protocol events — it's about how failures propagate across protocol layers and topological boundaries. This document catalogs the dependency chains that amplify blast radius from a single point of failure.

---

## Chain Type 1: Physical → OSPF → BGP (The Classic Stack)
**Trigger**: Physical link goes down (L1/L2 failure or `interface shutdown`)

**Chain**:
1. Interface goes down → interface route removed from RIB
2. OSPF detects neighbor loss (BFD sub-second OR dead interval timer)
3. OSPF sends LSA with link marked down
4. SPF recomputed on all routers in area
5. Routes that used the failed link as a segment are updated
6. BGP next-hop re-evaluation triggered (scan timer, default 5s)
7. BGP prefixes whose recursive next-hop resolved through the failed link become invalid
8. BGP withdraws those prefixes from FIB
9. Traffic to destinations behind those prefixes → NO_ROUTE

**Timing** (without BFD):
- OSPF detection: dead interval (40s default)
- SPF computation: immediate after LSA received
- BGP scan timer: 5s default
- Total blast radius realization: 45–60s

**Timing** (with BFD):
- BFD detection: 300ms–1s
- OSPF/BGP update: near-immediate
- Total blast radius realization: 1–2s

**D-dimension mapping**:
- D1: BGP sessions on the failed interface torn down (direct eBGP)
- D2: BGP prefixes whose next-hop chain included the failed link
- D3: Destinations reachable only via that link
- D5: If no redundant path exists

---

## Chain Type 2: Loopback Shutdown → iBGP Loss → Full Network Partition
**Trigger**: Loopback interface shut down on a core router

**Topology assumption**: Core router R_CORE uses its loopback as the source for all iBGP sessions. All other routers peer iBGP to R_CORE's loopback.

**Chain**:
1. `shutdown` applied to Loopback0 on R_CORE
2. Loopback0 prefix removed from OSPF (if redistributed) or directly from RIB
3. All iBGP sessions sourced from Loopback0 → TCP connection fails (or BGP declares NEXT_HOP unreachable)
4. All iBGP peers withdraw routes learned from R_CORE
5. If R_CORE was a Route Reflector: ALL clients lose all reflected routes
6. Full network partition

**Blast radius (RR scenario)**:
- D1: N sessions lost (N = number of RR clients)
- D2: All prefixes reflected by R_CORE
- D3: Network-wide reachability depends on whether clients had direct paths
- D5: If R_CORE RR was the only reflection point

**Why this matters**: A loopback shutdown is a common maintenance operation ("let me take this router out of service gradually"). Engineers sometimes forget that the loopback is the source for ALL iBGP sessions.

---

## Chain Type 3: AS_PATH Filter Loop → Route Suppression → Silent Black Hole
**Trigger**: AS_PATH access-list deployed that inadvertently matches legitimate routes

**Example**:
```
ip as-path access-list 10 deny _65100_   ! intended to deny transit AS 65100
ip as-path access-list 10 permit .*

route-map INBOUND_FILTER deny 10
 match as-path 10
route-map INBOUND_FILTER permit 20
```

**Intended**: deny routes that transit AS65100.
**Actual**: if `_65100_` regex also matches `_651000_` or `_165100_` (regex is not anchored to exact AS), more routes are filtered than intended.

**Chain**:
1. Route-map applied to neighbor
2. Routes whose AS_PATH matches (accidentally) are denied
3. Those routes disappear from RIB silently — no alarm, no NOTIFICATION
4. Traffic to those destinations → NO_ROUTE
5. D3 impact discovered only when users report connectivity issues

**Blast radius**:
- D2: All prefixes with AS_PATH matching the regex
- D3: All destinations behind those prefixes
- D1: Zero
- Silent failure — very hard to detect

**BGP regex pitfall**: IOS `_65100_` means "preceded by non-digit, followed by non-digit". This matches `65100` as a standalone AS. But sloppy regex can match unintended ASes. Always test with `show ip bgp regexp _65100_` before applying to a neighbor.

---

## Chain Type 4: Default Route Withdrawal → Internet Loss for All Customers
**Trigger**: ISP upstream stops advertising default route OR inbound route-map starts filtering it

**Topology**: Enterprise router R_EDGE with eBGP to upstream ISP. R_EDGE receives default route (`0.0.0.0/0`) from ISP and redistributes it into iBGP for internal routers.

**Chain**:
1. ISP stops advertising `0.0.0.0/0` (or R_EDGE's inbound filter blocks it)
2. Default route removed from R_EDGE's RIB
3. `redistribute bgp` in IGP removes the default from OSPF
4. All internal routers lose default route
5. All Internet-bound traffic (destined for non-internal prefixes) → NO_ROUTE

**Blast radius**:
- D2: Only 1 "prefix" lost (0.0.0.0/0) but impacts ALL Internet reachability
- D3: Every Internet destination becomes unreachable
- D1: Internal iBGP sessions unaffected

**Key insight**: D2 measured as "count of lost prefixes" severely underestimates this blast radius. The default route is 1 prefix but covers all Internet address space.

---

## Chain Type 5: Policy-Based Routing (PBR) Misconfiguration
**Trigger**: PBR applied to an interface redirects traffic to a different next-hop based on match criteria.

**Scenario**: 
- `route-map PBR permit 10` matches `ip address 101` (ACL 101 = `permit ip 10.0.0.0 0.255.255.255 any`)
- Sets next-hop to 192.168.99.1 (a management-only link)
- All traffic from 10.0.0.0/8 sources is now sent out the management interface

**Chain**:
1. PBR match is evaluated before routing table lookup
2. Traffic matching ACL 101 bypasses normal FIB
3. Traffic is forwarded to management next-hop (possibly congested or filtered)
4. Management link becomes congested or traffic is dropped by security policy
5. D3 impact: all traffic from 10.0.0.0/8 sources is dropped

**Blast radius**:
- D3: All traffic from 10/8 source space
- D4: Massive waypoint violation — traffic goes through management network
- D1/D2: Zero — BGP/routing table unaffected

**Batfish can model PBR** (routing policy question). PBR is one of the less-tested Batfish features; verify behavior before relying on it for grading.

---

## Chain Type 6: MED Causing Route Oscillation → Traffic Engineering Instability
**Scenario**: Two upstream providers, Provider A and Provider B. MED is used to prefer Provider A for prefix `10.10.0.0/16`. A misconfiguration causes MED to be set and then unset repeatedly (e.g., two competing route-maps applied in wrong order).

**Chain**:
1. MED oscillates between 0 and 100 for Provider A's route
2. BGP decision process alternates between Provider A (MED=0) and Provider B (MED=100)
3. Best path changes → route UPDATE sent to peers
4. Peers' BGP processes new UPDATE → their traffic shifts
5. If the oscillation is fast enough, peers may experience continuous churn

**Blast radius**:
- D7: Continuous forwarding path changes
- D4: Waypoint alternating between A and B
- D1/D2: Zero (sessions up, prefixes present)

**Operational detection**: Hard to detect with standard monitoring. Only visible in BGP update rate counters or traceroute output showing alternating paths.

---

## Compound Scenario: Metro PoP Failure (Realistic Multi-Chain)
**Scenario**: A metropolitan PoP (point of presence) has:
- 2 eBGP sessions to upstream ISPs (ISP_A, ISP_B)
- 1 iBGP session to core via MPLS
- OSPF adjacency to core for BGP next-hop resolution
- BFD enabled on OSPF adjacency

**Trigger**: OSPF BFD session on the core link has 50ms interval, multiplier 3 (150ms detection). A brief CPU spike causes 3 missed BFD packets.

**Chain**:
1. BFD detects false failure on core link
2. OSPF adjacency torn down
3. Core prefix (loopback of core router) removed from OSPF RIB
4. iBGP session to core uses core loopback as update-source → next-hop unresolvable → iBGP session drops
5. All routes learned via iBGP from core are withdrawn
6. Meanwhile, eBGP sessions to ISP_A and ISP_B are still up
7. But without iBGP routes, the PoP can't reach internal destinations
8. External customers at the PoP can reach the Internet (via ISP_A/B) but not internal services
9. BFD recovers after 150ms; OSPF comes back; iBGP re-establishes; routes reinstalled
10. Total disruption: 5–15 seconds (OSPF convergence + BGP scanner)

**D-dimension**:
- D1: 1 iBGP session lost transiently
- D2: All internal prefixes transiently lost
- D3: All internal-destination traffic disrupted for 5–15s
- Appears in monitoring as a "blip" — often attributed to "transient network issue" without root cause analysis

**This scenario demonstrates**: BFD timer misconfiguration has high blast radius risk even when the failure is transient and self-recovering. The 150ms "improvement" over 40s dead interval becomes a liability when there is CPU jitter.
