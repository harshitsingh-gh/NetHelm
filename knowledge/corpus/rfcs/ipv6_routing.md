# IPv6 Routing — OSPFv3, BGP MP-BGP IPv6, and Blast Radius

## Overview
IPv6 routing uses the same fundamental protocols as IPv4 but with important differences. NetConfEval covers IPv4 exclusively — this document covers the IPv6 gaps.

## Key IPv6 Routing Differences from IPv4

### Address Space
- 128-bit addresses (vs 32-bit): written as 8 groups of 4 hex digits, e.g., `2001:db8::/32`
- Link-local addresses (fe80::/10): auto-configured on every interface; used for neighbor discovery and routing protocol hellos
- Loopback: `::1/128`
- Documentation range: `2001:db8::/32`
- Global unicast: `2000::/3`
- ULA (Unique Local Addresses): `fc00::/7` — roughly equivalent to RFC 1918 for IPv4

### Dual-Stack
Most networks operate dual-stack: IPv4 and IPv6 simultaneously. A single router interface has both an IPv4 and IPv6 address. Routing protocols run independently for each address family (except MP-BGP, which carries both).

## OSPFv3 (RFC 5340) — OSPF for IPv6

### Key Differences from OSPFv2
- **Protocol number**: 89 (same as OSPFv2) but IPv6 protocol field
- **Adjacency**: uses link-local addresses for hello/DR/BDR communication
- **No subnet mask in hello**: OSPFv3 is address-family-agnostic — the protocol works the same for IPv4 and IPv6
- **Link-local scope**: hellos and some flooding are link-local scoped
- **New LSA types**: Link LSA (type 8, link-local scope), Intra-Area-Prefix LSA (type 9, replaces router LSA's IPv4 prefix info)

### OSPFv3 LSA Types
- Type 1 (Router LSA): same as OSPFv2 — adjacencies only, no prefixes
- Type 2 (Network LSA): multi-access segment DR
- Type 3 (Inter-Area Prefix LSA): inter-area IPv6 prefixes from ABRs
- Type 4 (Inter-Area Router LSA): location of ASBR
- Type 5 (AS External LSA): external IPv6 prefixes
- Type 7 (NSSA LSA): NSSA external prefixes
- **Type 8 (Link LSA)**: per-link, link-local scope; distributes link-local prefix of the router + option bits
- **Type 9 (Intra-Area-Prefix LSA)**: carries all IPv6 prefixes for a router or transit network

### OSPFv3 Blast Radius
Same patterns as OSPFv2 (RFC 2328) with:
- Additional blast radius: IPv6 routes lost while IPv4 routes remain (if dual-stack running separate OSPFv2/v3 processes)
- Link-local adjacency dependency: if link-local address is misconfigured, OSPFv3 adjacency fails but OSPFv2 continues

### FRR Config (OSPFv3)
```
interface eth0
 ipv6 ospf6 area 0.0.0.0
 ipv6 ospf6 cost 10
!
router ospf6
 ospf6 router-id 1.1.1.1
 area 0.0.0.0 range 2001:db8::/48
```

## MP-BGP for IPv6 (RFC 4760)
BGP carries IPv6 prefixes via MP-REACH_NLRI and MP_UNREACH_NLRI attributes with AFI=2, SAFI=1 (IPv6 unicast).

### IPv6 BGP Session
```
router bgp 65001
 neighbor 2001:db8::2 remote-as 65002
 !
 address-family ipv6 unicast
  neighbor 2001:db8::2 activate
  network 2001:db8:1::/48
```

### IPv6 Next-Hop Handling
- BGP NEXT_HOP for IPv6 routes: can be either a global IPv6 address or a link-local address
- Link-local next-hops require the next-hop to be on a directly-attached interface
- When redistributing from OSPFv3 to BGP: next-hop is the advertising router's loopback or link address

### IPv6-Specific Blast Radius Patterns

#### Pattern: RA (Router Advertisement) Disruption
Not a routing protocol blast radius, but impactful:
- IPv6 hosts use SLAAC (Stateless Address Autoconfiguration, RFC 4862) or DHCPv6
- If Router Advertisements stop (interface `ipv6 nd ra-suppress` or `no ipv6 nd` config change), hosts lose their ability to auto-configure
- This is NOT visible in Batfish (RA is a link-local control mechanism)

#### Pattern: Dual-Stack Asymmetry (IPv4 up, IPv6 down)
**Scenario**: OSPF adjacency up, OSPFv3 adjacency down (different authentication or hello interval).
**Effect**: IPv4 traffic flows normally; IPv6 traffic black-holes.
**Hard to detect**: IPv4 monitoring shows healthy; IPv6-only users (or applications using IPv6 by default) experience complete failure.
**Batfish**: Would show IPv6 prefixes missing from bgpRib or OSPFv3 routes missing, even if IPv4 is intact.

#### Pattern: IPv6 Prefix Aggregation Error
Same as IPv4 aggregate masking (Pattern 16 in advanced_patterns.md) but for IPv6 prefixes:
- `aggregate-address 2001:db8::/32 summary-only` covers all more-specifics
- Removing a component `/48` from the RIB → that space blackholed even though `/32` still advertised

## IPv6 Transition Mechanisms (6to4, 6PE, 6VPE)
**6PE (RFC 4798)**: IPv6 Provider Edge — carries IPv6 over an MPLS IPv4 core:
- CE sends IPv6 traffic to PE
- PE encapsulates in MPLS (two labels: transport + VPN-like label for 6PE)
- Delivered to remote PE which decapsulates and forwards IPv6

**Blast radius**: same as L3VPN blast radius patterns, but for IPv6 customers.

## Batfish IPv6 Support
Batfish has **good IPv6 support** for:
- IPv6 prefix routing in bgpRib
- OSPFv3 adjacencies and routes (partial — depends on platform)
- IPv6 traceroute (reachability checks)
- **For NetHELM**: IPv6 prefix blast radius (D2 dimension) can be measured for BGP IPv6 routes
