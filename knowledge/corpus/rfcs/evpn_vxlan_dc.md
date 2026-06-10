# EVPN and VXLAN — Data Center Overlay Networking

## Overview
EVPN (Ethernet VPN, RFC 7432) is a BGP-based control plane for distributing MAC/IP reachability information across a network. VXLAN (Virtual eXtensible LAN, RFC 7348) is the most common data-plane encapsulation used with EVPN in data center fabrics. Together, they form the dominant DC fabric technology replacing STP/MLAG architectures.

## VXLAN Fundamentals
VXLAN encapsulates L2 Ethernet frames in UDP packets (destination port 4789). Each VXLAN tunnel is identified by a 24-bit VNI (VXLAN Network Identifier). VNI serves the same purpose as VLAN ID but in the overlay.

**VTEP (VXLAN Tunnel Endpoint)**: device that originates/terminates VXLAN tunnels. In a modern DC fabric, VTEPs are typically the TOR (Top of Rack) switches.

**Encapsulation format**:
- Outer IP header: VTEP source IP → VTEP destination IP
- UDP header: source port (hash of inner header), dst 4789
- VXLAN header: 24-bit VNI
- Inner Ethernet frame: original L2 packet

## EVPN Route Types
EVPN uses BGP AFI=25, SAFI=70. There are 5 primary route types (more exist for specific use cases):

| Type | Name | Purpose |
|---|---|---|
| Type 1 | Ethernet Auto-Discovery | Fast MAC mobility, ES (Ethernet Segment) per-EVI advertisement |
| Type 2 | MAC/IP Advertisement | Distribute MAC addresses and ARP (IP→MAC) bindings |
| Type 3 | Inclusive Multicast Ethernet Tag | BUM (Broadcast, Unknown, Multicast) traffic flooding |
| Type 4 | Ethernet Segment Route | Designated Forwarder election for multi-homed segments |
| Type 5 | IP Prefix Route | L3 routing between VNIs/VRFs (asymmetric or symmetric IRB) |

## DC Fabric Architecture (Spine-Leaf / Clos)
```
        [Spine1]  [Spine2]
         /    \   /    \
     [Leaf1][Leaf2][Leaf3][Leaf4]
       |       |       |       |
     [TOR]  [TOR]   [TOR]   [TOR]
      |       |       |       |
   Servers  Servers Servers Servers
```
- All Leaf ↔ Spine links are L3 routed (IP underlay)
- ECMP across all spine links (typically 2–8 spines)
- VXLAN tunnels between VTEPs (leaf switches) for overlay traffic
- BGP EVPN control plane for MAC/IP distribution

## BGP EVPN Configuration (Arista/Cumulus style)
```
router bgp 65001
 neighbor EVPN-CORE peer-group
 neighbor EVPN-CORE remote-as 65000
 neighbor EVPN-CORE update-source Loopback0
 neighbor EVPN-CORE ebgp-multihop 3
 neighbor EVPN-CORE send-community extended
 !
 address-family evpn
  neighbor EVPN-CORE activate
 !
 vlan 10
  rd 1.1.1.1:10010
  route-target import export 1:10010
  redistribute learned
```

## EVPN Blast Radius Patterns

### Pattern: VTEP Failure (Leaf Switch Crash)
**Trigger**: A leaf switch (VTEP) fails.
**Chain**:
1. BGP EVPN sessions to spine peers torn down
2. All Type 2 routes (MAC/IP) advertised by this VTEP are withdrawn
3. Remote VTEPs remove MAC/ARP entries for servers on the failed leaf
4. Traffic from other servers to servers on the failed leaf → MAC resolution fails → BUM flooding (if configured) or drop
5. If multi-homed (MLAG/ESI-LAG): traffic fails over to the surviving leaf

**D-dimensions**:
- D1: All BGP EVPN sessions from failed leaf
- D2: All MAC/IP prefixes (Type 2 routes) for servers on that leaf; all Type 5 IP prefix routes
- D3: All servers on the failed leaf unreachable
- D5: If servers were single-homed: complete loss; if multi-homed: failover to surviving leg

### Pattern: Spine Failure (BGP Route Reflector / Underlay Fabric)
**In a spine-leaf fabric, spines are typically BGP route reflectors for the EVPN overlay.**

**Trigger**: One spine fails.
**Chain**:
1. All leaf BGP EVPN sessions to that spine drop
2. EVPN route reflector loses those clients; routes not withdrawn (still available via other spine)
3. ECMP paths through failed spine removed from underlay
4. Overlay VXLAN tunnels that used the failed spine for underlay routing reconverge to remaining spines

**D-dimensions**:
- D1: BGP sessions to failed spine (from all leaves)
- D5: Redundancy reduced from 2 spines to 1 (50% reduction)
- D7: VXLAN tunnel underlay paths change (traffic now goes through remaining spine)
- **If only 2 spines and both fail**: D3 (complete loss of inter-leaf communication)

### Pattern: BGP EVPN Route Target Mismatch
**Trigger**: VNI 100 export RT on Leaf A is 65001:100; import RT on Leaf B is 65001:200.
**Effect**: MAC/IP routes from Leaf A are not imported into Leaf B's bridge domain for VNI 100.
**D2**: All MAC addresses from Leaf A's VNI 100 invisible on Leaf B
**D3**: Servers in VNI 100 on Leaf A cannot communicate with servers in VNI 100 on Leaf B
**Silent failure**: BGP sessions up; no errors; just missing MAC entries

### Pattern: Type 3 (BUM) Route Missing
**Trigger**: Type 3 Inclusive Multicast Ethernet Tag route not generated or filtered for a VNI.
**Effect**: Broadcast, Unknown-unicast, and Multicast traffic for that VNI cannot be flooded.
**Consequences**:
- ARP requests not flooded → new servers cannot resolve MACs of existing servers
- Unknown MAC destinations → dropped instead of flooded
- First-packet loss for any new communication until ARP/MAC is resolved via Type 2

### Pattern: Asymmetric vs. Symmetric IRB and Blast Radius
**Asymmetric IRB**: VXLAN routing happens at the ingress VTEP; both VTEPs must have all VLANs configured.
**Symmetric IRB**: Uses L3VNI; routing done centrally; only ingress and egress VTEPs need the VLAN.

**Blast radius difference**:
- Asymmetric: if a VLAN is missing on any VTEP → D3 for that VLAN's traffic going to that VTEP
- Symmetric: VLAN only needs to exist on access VTEPs; failure more isolated

### Pattern: VXLAN Underlay MTU Issue
**Trigger**: VXLAN encapsulation adds 50 bytes (14 outer Eth + 20 IP + 8 UDP + 8 VXLAN). If underlay MTU = 1500, inner MTU = 1450 — too small for most applications (default 1500 inner MTU expected).
**Effect**: Large packets silently dropped; small packets work fine → asymmetric connectivity
**D3**: Intermittent reachability failure for specific traffic patterns (large transfers fail, pings succeed with small payloads)
**Detection**: Very hard — ICMP pings succeed (small), TCP sessions drop for large file transfers. Classic "works from ping, breaks for applications" pattern.

## Multi-Homing with EVPN ESI (Ethernet Segment Identifier)
ESI-based multi-homing connects a server or CE to two VTEPs simultaneously:
- Both VTEPs advertise Type 1 and Type 4 routes for the ESI
- Designated Forwarder (DF) election: one VTEP is the active forwarder per VLAN (to prevent duplicate BUM flooding)
- If one VTEP fails: other VTEP takes over; Type 4 re-election happens

**Blast radius of DF failure**:
- D1: BGP sessions on failed VTEP
- D5: Redundancy lost for that ESI segment
- Transient D3: during DF re-election (~1–5s)

## EVPN and Batfish
Batfish has **partial EVPN support**:
- BGP EVPN session status (bgpSessionStatus) works for EVPN sessions
- Type 2 (MAC/IP) routes may be visible in bgpRib depending on platform/version
- Type 3/4/5 routes: limited or no support
- VXLAN data-plane forwarding: NOT modeled
- For NetHELM: use BGP session and prefix counts as proxy; EVPN-specific grading requires additional tooling

## RIFT DC Protocol (NetConfEval Step 3)
RIFT (Routing in Fat-Trees) is an alternative to BGP EVPN + OSPF/IS-IS underlay for DC fabrics:
- Specifically designed for Clos/fat-tree topologies
- Combines link-state (northbound — toward spine) and distance-vector (southbound — toward leaf)
- Self-configuring: nodes automatically discover topology and assign levels
- Avoids the complexity of BGP policy for DC underlay
- **Levels**: Leaf=1, Spine=2+, ToF (Top of Fabric) = max level
- FRR supports an experimental RIFT implementation (`riftd`)

**RIFT blast radius**: simpler than BGP EVPN because there's no complex policy. Key failure modes:
- Level misconfiguration: Leaf marked as ToF → routing loops
- LIE (Link Information Element) address mismatch: LIE multicast address changed → adjacency loss
- System ID collision: two nodes with same system ID → topology inconsistency
