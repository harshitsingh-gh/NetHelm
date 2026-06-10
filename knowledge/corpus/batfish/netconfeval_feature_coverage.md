# NetConfEval Feature Coverage Analysis vs. NetHELM Requirements

## Source: Analysis of RedHatResearch/conext24-NetConfEval (CoNEXT 2024)

## NetConfEval's Three Evaluation Steps

### Step 1: High-Level Requirement Translation (3,554 policy instances)
Translates natural language network requirements to formal specification.
Policy types covered:
- **Reachability** (1,056 instances): "node A can reach prefix P"
- **Waypoint** (977 instances): "path from A to P must include node W"
- **LoadBalancingSimple** (1,167 instances): "path from A to P uses N equal-cost paths"
- **Isolation** (354 instances): "node A must NOT reach prefix P"
- **Conflict detection**: detect contradictory requirements (e.g., "A can reach P" vs "A cannot reach P")

**Network topology**: European ISP-like topology with city names as nodes (madrid, london, paris, etc.)
**Protocols**: abstract — no specific protocol; tests translation ability

### Step 2: Traffic Engineering Code Generation (16 test cases, 4 categories)
Generates Python functions that compute routing paths satisfying requirements:
- **Shortest path**: compute shortest path in a graph given reachability requirements
- **Reachability**: verify reachability between all node pairs
- **Waypoint**: shortest path with mandatory waypoints
- **Load balancing**: find N equal-cost paths

**Protocol-independent** — tests algorithmic/programming ability, not networking protocol knowledge.

### Step 3: Low-Level Configuration Generation (5 scenarios)
Generates complete router configurations from natural language descriptions:

| Scenario | Protocol | Nodes | Key Features |
|---|---|---|---|
| bgp_simple | BGP (FRR bgpd) | 2 | eBGP, single session, network statement, no policies |
| ospf_simple | OSPF (FRR ospfd) | 5 (bb0-bb4) | Single area 0, custom costs, redistribute connected |
| ospf_multiarea | OSPF (FRR ospfd) | 11 (bb0-bb4, r1-r6) | 4 areas (0+3 stubs), ABRs, multiple costs |
| rip | RIP (FRR ripd) | 4 | Basic RIP, redistribute connected |
| rift_dc | RIFT (FRR riftd) | 10 (4 leaf, 4 spine, 2 ToF) | Fat-tree, levels, LIE address, system IDs, prefixes |

---

## Feature Coverage Gap Analysis

### Protocols NOT Covered by NetConfEval

| Protocol | Gap | Blast Radius Relevance | Batfish Gradeable? |
|---|---|---|---|
| **IS-IS** | Completely absent | High (SP core IGP) | Partial |
| **IPv6 (OSPFv3, BGP IPv6)** | Absent | Medium-High | Yes (BGP IPv6 good) |
| **MPLS/LDP** | Absent | Very High (SP core) | No |
| **L3VPN (RFC 4364)** | Absent | Very High (VPN service) | No |
| **EVPN/VXLAN** | Absent | High (DC fabric) | Partial |
| **Multicast (PIM)** | Absent | Medium (video/finance) | No |
| **Segment Routing** | Absent | High (modern TE) | No |
| **RSVP-TE** | Absent | Medium (legacy TE) | No |
| **BGP policies** | Absent | Very High | YES |
| **iBGP / Route Reflectors** | Absent | Very High | YES |
| **BGP communities** | Absent | High | Partial |
| **HSRP/VRRP** | Absent | Medium | No |
| **ACL/security policy** | Absent | Medium | YES (searchFilters) |
| **QoS / DSCP** | Absent | Low | No |
| **VLAN/STP (L2)** | Absent | Medium | Partial |

### Policy Complexity Gaps in NetConfEval BGP
The bgp_simple scenario covers:
- eBGP session setup
- Basic network announcement
- 2 routers only

Missing from bgp_simple and completely untested:
- Inbound/outbound route-maps
- Prefix-list filtering
- AS-path access-lists
- Community matching
- LOCAL_PREF / MED / weight manipulation
- AS_PATH prepending
- Maximum-prefix limits
- next-hop-self
- Update-source (iBGP loopback peering)
- Route Reflector configuration (route-reflector-client)
- Peer groups
- BGP confederation
- Graceful restart
- Multi-homed BGP with path selection
- Conditional advertisement

### Topology Complexity Gaps
NetConfEval scenarios are small (2–11 nodes). Missing:
- SP-scale topologies (100+ nodes)
- Redundant multi-homed designs (dual-homed ASes)
- Route Reflector hierarchies (two-level RR)
- PE/P/CE MPLS topologies
- DC spine-leaf fabrics (beyond RIFT)
- Partial mesh BGP with specific peering policies

---

## NetHELM Coverage Expansion Strategy

### Batfish-Gradeable Features (High Priority — V1)
These features can be graded by Batfish, making them viable for the paper's V1:

1. **BGP policy (route-maps, prefix-lists, communities, LOCAL_PREF)** — D2, D6
2. **iBGP with Route Reflectors** — D1, D2, D3 (split-horizon scenarios)
3. **BGP next-hop-self / recursive resolution** — D2, D3
4. **IPv6 BGP prefixes** — D2, D3 (same oracle works)
5. **OSPF redistribution into BGP** — D2, D3
6. **Multi-area OSPF ABR filtering** — D2, D3
7. **ACL changes via searchFilters** — D6
8. **Null route injection** — D3 (traceroute shows NO_ROUTE)
9. **Static route manipulation** — D2, D3

### Lab-Gradeable Features (Medium Priority — V1.5)
These require FRR lab but not Batfish:

1. **BFD-triggered failures** — D1 (verify in lab that session drops as expected)
2. **IS-IS adjacency changes** — D7, D3 (FRR isisd supports IS-IS)
3. **RIP convergence** — D2, D3 (FRR ripd present in NetConfEval)
4. **RIFT level misconfiguration** — D3 (FRR riftd)
5. **Multicast (PIM) RP failure** — D3 (requires PIM config in lab)

### Out of Scope for NetHELM V1 (Document as Limitation)
1. MPLS/LDP/RSVP-TE (Batfish cannot grade)
2. EVPN/VXLAN data plane (Batfish partial; complex to verify)
3. SRv6 / SR-MPLS (Batfish cannot grade)
4. Multicast state (Batfish cannot grade)
5. HSRP/VRRP (Batfish cannot grade)

---

## Scenarios Count Per Protocol (NetHELM V1 Target)

| Protocol/Feature | Target Scenario Count | Status |
|---|---|---|
| BGP policies (route-map, prefix-list, community) | 30 | Planned |
| iBGP / Route Reflectors | 15 | Planned |
| BGP recursive next-hop chains | 10 | Partial (frr_square) |
| OSPF multi-area blast radius | 10 | Planned |
| OSPF redistribution into BGP | 8 | Planned |
| IS-IS adjacency (lab) | 5 | Future |
| RIP convergence | 5 | Future |
| IPv6 BGP | 5 | Future |
| ACL changes (D6) | 10 | Planned |
| Null route / RTBH | 5 | Partial |
| **TOTAL V1 target** | **~100** | |

Current frr_square lab has ~20 scenarios. Need 80 more for a publishable N.
