# Segment Routing (SR-MPLS and SRv6) — Reference and Blast Radius

## Overview
Segment Routing (RFC 8402) is a source-routing paradigm where the ingress node programs the complete forwarding path by encoding it as an ordered list of "segments" in the packet header. Unlike RSVP-TE, SR requires no per-flow state in the network — only the source node maintains state.

**Two data planes**:
- **SR-MPLS**: segments encoded as MPLS labels (uses existing MPLS infrastructure)
- **SRv6**: segments encoded as IPv6 addresses (uses IPv6 routing)

## SR-MPLS

### Segment Types
- **Node Segment (Prefix SID)**: identifies a node (router); instructs forwarding toward that node via shortest path. Globally unique across the SR domain.
- **Adjacency Segment (Adj-SID)**: identifies a specific link/adjacency; dynamically allocated (local significance). Used for explicit path specification.
- **Anycast Segment**: identifies a group of nodes; traffic forwarded to nearest in group.
- **Binding Segment (BSID)**: maps a segment to an SR policy (used for hierarchical TE).

### SRGB (Segment Routing Global Block)
A reserved range of MPLS labels allocated for Prefix SIDs. Default: 16000–23999 on most platforms.
Each router is assigned a unique SID index within this range. Absolute label = SRGB_base + SID_index.

### SR-MPLS Forwarding
```
Ingress router label stack: [node_SID_egress, adj_SID_waypoint]
  → Packet forwarded to waypoint via adj-SID
  → Waypoint pops adj-SID; forwards to egress via node-SID (shortest path)
  → Egress pops node-SID; delivers IP packet
```

### Control Plane: SR with IS-IS or OSPF
SR extensions to IS-IS (RFC 8667) and OSPF (RFC 8665) distribute:
- Router SID (Prefix SID for loopback)
- Adjacency SIDs
- SRGB range

No separate LDP or RSVP-TE required — SR is carried in the existing IGP.

### SR-TE (Traffic Engineering with Segment Routing)
SR-TE policies define explicit paths for traffic engineering:
```
Segment-list: [adj-SID1, adj-SID2, ..., node-SID-egress]
Color: TE policy identifier (integer)
Preference: higher = preferred when multiple policies match
Binding SID: single label that maps to the entire segment list
```

**Headend** (ingress): matches traffic to a color/endpoint; pushes the segment list
**PCE (Path Computation Element)**: centralized controller that computes SR-TE paths (RFC 8283)

## SR-MPLS Blast Radius Patterns

### Pattern: Node SID Collision
**Trigger**: Two routers assigned the same SID index.
**Effect**: MPLS label collision. Traffic labeled with the conflicting label may be forwarded to either router unpredictably.
**D4**: Waypoint violations — traffic intended for Router A may reach Router B.
**D3**: If Router B doesn't have the destination route, traffic drops.
**Detection**: IS-IS/OSPF will log the collision; some platforms silently prefer the first-seen SID.

### Pattern: SRGB Range Mismatch
**Trigger**: Routers in the same SR domain have different SRGB_base values (e.g., one uses 16000, another uses 17000).
**Effect**: Absolute SID labels differ by router; label forwarding is incorrect.
**Full blast radius**: all SR-MPLS traffic in the domain affected; complete forwarding failure.
**This is a critical Day-0 configuration check** — SRGB must be consistent across all SR nodes.

### Pattern: Adjacency SID Not Programmed
**Trigger**: SR-TE policy references an adj-SID that wasn't generated (interface not participating in SR, or adj-SID allocation failure).
**Effect**: Packet with stale/invalid adj-SID reaches a node that doesn't have that label in its LFIB → packet dropped.
**D3**: Traffic for the affected SR-TE policy drops completely.

### Pattern: SR-TE Policy Headend Change
**Trigger**: BGP SR-TE policy (via BGP-LS or PCEP) changes the segment list for an active policy.
**Effect**: Traffic shifts to the new path immediately (no LDP reconvergence required; SR is per-path in packet).
**D7**: Forwarding path changes for affected traffic class.
**Advantage vs RSVP-TE**: change is applied in milliseconds; RSVP-TE requires re-signaling.

### Pattern: Midpoint Node Failure (SR vs RSVP comparison)
**RSVP-TE failure**: midpoint failure requires make-before-break (establish new LSP before tearing old one) or FRR bypass tunnel activation (~50ms). Without FRR: path must be completely re-signaled.
**SR-MPLS failure**: ingress node re-computes the segment list and installs new labels. No per-hop state to update. FRR still applies at the per-segment level (TI-LFA).

**Blast radius (SR vs RSVP)**: SR has lower blast radius for midpoint failures because:
- No per-hop state to clean up
- Reconvergence driven by IGP convergence (already fast) + headend update
- TI-LFA provides 50ms protection without RSVP complexity

### Pattern: SR-MPLS TTL Misconfiguration
**In SR-MPLS**: by default, TTL is propagated from IP header to MPLS. If TTL=64 in the IP header and the SR path is 5 hops, TTL reaches 59 at egress — still valid. But some platforms don't decrement TTL at the PHP node (MPLS TTL processing disabled), causing TTL mismatch.
**Effect**: Some traceroute tools show inconsistent hop counts through SR tunnels; not a blast-radius issue but a diagnostic confusion.

## SRv6 (Segment Routing over IPv6)

### Architecture
SRv6 encodes segments as IPv6 addresses. The Segment Routing Header (SRH, RFC 8754) is inserted into the IPv6 packet.

**SRH format**: Next Header, Hdr Ext Len, Routing Type=4, Segments Left, Last Entry, Flags, Tag, Segment List[]

**SID structure (RFC 8986)**: Locator:Function:Argument
- Locator: routed IPv6 prefix (analogous to SRGB + SID)
- Function: operation to perform (End, End.X, End.DX4, End.DT4, etc.)
- Argument: per-packet variable (e.g., flow ID)

### SRv6 Functions
- **End**: basic forwarding — decrement Segments Left, update destination address
- **End.X**: forward out specific interface (adjacency SID equivalent)
- **End.DX4**: decapsulate and forward as IPv4 (L3VPN equivalent)
- **End.DT4**: decapsulate and lookup in IPv4 VRF (L3VPN)
- **End.DT6**: decapsulate and lookup in IPv6 VRF
- **End.B6.Encaps**: encapsulate in new SRv6 header (binding segment)

### SRv6 Blast Radius Patterns
- **Locator prefix withdrawal**: SRv6 locator is an IPv6 prefix in the IGP. If withdrawn, traffic for that node's SIDs is dropped. D2 (prefix lost) + D3 (all services using that SID unreachable).
- **MTU**: SRH adds overhead (minimum 8 + 16N bytes for N segments). Path MTU must accommodate. MTU mismatch → fragmentation or drop for large packets.
- **No SRH support on transit**: if a P node on the path doesn't support SRv6, it may drop packets with unknown IPv6 extension headers (depends on configuration).

## Batfish SR Support
- SR-MPLS: **not modeled** (MPLS label-switching is out of scope)
- SRv6: **not modeled**
- **For NetHELM**: SR scenarios require real lab or emulator; Batfish cannot grade SR-specific blast radius
