# Maintenance Operations That Caused Network Outages — Pattern Library

## Overview
The majority of network outages are caused by changes, not spontaneous failures. This document catalogs maintenance operation patterns that have repeatedly caused outages, with analysis of the blast radius mechanism in each case.

---

## Maintenance Type 1: BGP Session Soft/Hard Reset During Traffic Hours
**Operation**: `clear ip bgp X.X.X.X` (hard reset) or `clear ip bgp X.X.X.X soft in/out`
**Intended purpose**: Apply new inbound/outbound policy without full session teardown (soft) or force re-establishment after config change (hard).

**Hard reset blast radius**:
- D1: 1 session torn down
- D2: All prefixes from that session withdrawn and re-learned
- D3: Up to 180s of traffic impact (Hold Timer duration + BGP convergence)
- **Never do this during peak traffic hours.**

**Soft reset blast radius**:
- D1: Zero (session stays up)
- D2: Prefixes re-evaluated against new policy; some may disappear if new policy is more restrictive
- D3: Only if new policy blocks previously accepted routes

**Common mistake**: Using hard reset when soft reset would suffice. With `soft-reconfiguration inbound` enabled, soft in is always safe.

---

## Maintenance Type 2: Applying a New Route-Map to an Existing Neighbor
**Operation**: Add `neighbor X.X.X.X route-map NEW_MAP in` to an existing BGP session.
**Effect**: On Cisco IOS, the new route-map takes effect on the NEXT UPDATE cycle. To force immediate application: `clear ip bgp X.X.X.X soft in`.

**Blast radius of soft clear after new route-map**:
- D2: Routes that the new map denies → withdrawn immediately
- D3: Destinations behind those routes → black hole
- Common mistake: new route-map has implicit deny-all at end; engineer forgets to add final `permit any`

---

## Maintenance Type 3: Route Reflector Migration
**Operation**: Migrating from full-mesh iBGP to Route Reflector topology.
**Steps**: (1) Add RR config, (2) Verify RR clients can reach each other, (3) Remove full-mesh sessions.

**Step 3 blast radius (if premature)**:
- If a client doesn't have the RR config yet, removing its full-mesh session = D1 (session lost) + D2 (routes lost)
- If RR has a bug in cluster config, routes may be reflected back to the client they came from (loop prevention may incorrectly suppress routes)

**Safe procedure**:
1. Add `route-reflector-client` to new clients one at a time
2. Verify each client's route table after adding RR relationship
3. Only remove full-mesh sessions after verifying RR is correctly reflecting all routes
4. Keep full-mesh as backup for 48h before removal

---

## Maintenance Type 4: AS Number Migration
**Operation**: An enterprise changes its AS number (e.g., after merger/acquisition).
**Mechanism**: All BGP sessions must be rebuilt with the new AS number. Old AS sessions are torn down.

**Blast radius**:
- D1: ALL BGP sessions simultaneously (if done without graceful migration)
- D2: ALL prefixes lost during transition
- D3: Complete outage during transition window

**Graceful AS migration (RFC 7705)**:
- `bgp local-as OLD_AS no-prepend replace-as` — allows a router to present itself as the old AS to existing peers while using the new AS internally
- Allows incremental migration peer by peer
- Blast radius reduced to one session at a time

---

## Maintenance Type 5: Prefix Deaggregation / Reaggregation
**Operation**: Change from advertising many specific routes to a single aggregate, or vice versa.

**Deaggregation (aggregate to specifics)**:
- More specific routes propagate globally
- Immediate D7 impact: traffic may prefer more-specific routes and shift forwarding paths
- If any specific doesn't match what was in the aggregate, D2 impact possible

**Reaggregation (specifics to aggregate)**:
- More-specific routes withdrawn
- If the aggregate covers the same space: D2=0, D3=0 (aggregate catches traffic)
- If any specific was reachable but NOT covered by aggregate: D2 (prefix lost), D3 (black hole)

---

## Maintenance Type 6: Null Route Injection (Temporary Black Hole)
**Operation**: NOC injects `ip route X.X.X.X/Y Null0` to black-hole DDoS traffic.
**Intended**: Drop traffic to/from specific source/destination.

**Blast radius if wrong prefix**:
- D3: All legitimate traffic to X.X.X.X/Y black-holed
- Duration: until static route is removed
- **Scope multiplier**: if the null route is redistributed into BGP (RTBH), it propagates to all edge routers

**Safe practice**: Always use /32 or /128 for RTBH, not /24 or broader. Verify the prefix ownership before injecting.

---

## Maintenance Type 7: OSPF Area Restructuring
**Operation**: Move a set of routers from one OSPF area to another.

**Blast radius during transition**:
- Routers in transition: OSPF adjacencies torn down; routes lost until re-established in new area
- Adjacent areas: summary routes change as ABR updates Type 3 LSAs
- BGP: if BGP uses OSPF for next-hop resolution, BGP route withdrawals cascade from OSPF disruption

**Common mistake**: Moving a router to a new area without ensuring the new area has connectivity to Area 0 (backbone). Non-backbone areas without virtual links to Area 0 become partitioned.

---

## Maintenance Type 8: MPLS Label Distribution Protocol (LDP) Restart
**Operation**: Restart LDP daemon on a P (provider core) router.

**Blast radius**:
- LDP sessions to all adjacent routers tear down
- MPLS LSPs transiting through this router lose their labels
- Traffic using those LSPs falls back to IP forwarding (if IP route exists) or drops (if IP fallback disabled)
- For BGP-free core: traffic that depends on MPLS label switching cannot be forwarded via IP routing (no BGP routes in the core); traffic drops completely

**D-dimension**:
- D3: All MPLS-forwarded traffic through the affected router is disrupted
- D1: BGP sessions unaffected (BGP runs over IP, which may be intact)
- D2: BGP prefixes in the RIB unaffected; but VPN routes may be unreachable if MPLS transport is broken

**NetHELM limitation**: Batfish does not fully model MPLS forwarding plane. MPLS blast radius requires additional tooling.

---

## Maintenance Type 9: VLAN/L2 Change Affecting BGP Underlay
**Operation**: Change native VLAN, STP topology, or VLAN membership on a switch that carries BGP peering sessions.

**Blast radius**:
- L2 change → L2 adjacency loss → L3 interface loses carrier → OSPF neighbor down → BGP next-hop unresolvable → BGP session down
- The BGP session loss is a consequence of an L2 change — engineers doing switch maintenance often don't think about BGP impacts
- STP topology change: new root bridge election → 30-second convergence with classic STP → BGP hold timer may expire if the path loss exceeds 60s

**This is the "unexpected BGP blast radius from non-BGP change" scenario class.**

---

## Pattern Summary: When One Change Causes Multi-Layer Blast Radius

| Primary change | Layer 2 impact | Layer 3 impact | BGP impact | Blast radius |
|---|---|---|---|---|
| Interface shutdown | Carrier loss | Routes withdrawn | Sessions down | D1+D2+D3 |
| VLAN change | Forwarding disruption | L3 adjacency loss | Session loss | D1+D2+D3 |
| OSPF cost change | None | New forwarding paths | Next-hop path change | D7+D4 |
| Static route change | None | Recursive resolution | BGP route install/withdraw | D2+D3 |
| BGP route-map change | None | None | Route filter | D2+D3+D6 |
| FlowSpec origination | None | None | Policy propagation | D6 → potentially D1 |
| MPLS LDP restart | None | MPLS disruption | VPN unreachable | D3 (MPLS scope) |
| AS number change | None | None | All sessions | D1+D2+D3 |
