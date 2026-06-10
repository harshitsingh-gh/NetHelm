# RFC 4271 — A Border Gateway Protocol 4 (BGP-4) Summary

## Overview
BGP-4 is the de facto inter-domain routing protocol of the Internet. It operates over TCP port 179. RFC 4271 (January 2006) is the normative specification, obsoleting RFC 1771.

## FSM States
BGP speakers maintain a per-neighbor finite state machine:
1. Idle — no TCP connection
2. Connect — waiting for TCP to complete
3. Active — TCP failed, retrying
4. OpenSent — TCP established, OPEN message sent
5. OpenConfirm — waiting for KEEPALIVE or NOTIFICATION
6. Established — session up, UPDATE messages exchanged

## Message Types
- OPEN (type 1): initiates session; carries AS number, hold time, BGP ID, optional parameters
- UPDATE (type 2): advertises or withdraws prefixes; contains NLRI, path attributes, withdrawn routes
- NOTIFICATION (type 3): error; causes session tear-down; carries Error Code + Subcode
- KEEPALIVE (type 4): maintains session (sent ≤ 1/3 of hold time)
- ROUTE-REFRESH (type 5, RFC 2918): requests re-advertisement of all routes

## Path Attributes
- ORIGIN (type 1, well-known mandatory): IGP=0, EGP=1, INCOMPLETE=2
- AS_PATH (type 2, well-known mandatory): sequence of AS numbers traversed
- NEXT_HOP (type 3, well-known mandatory): IPv4 next-hop address
- MULTI_EXIT_DISC / MED (type 4, optional non-transitive): tie-break between multiple entry points to same AS
- LOCAL_PREF (type 5, well-known discretionary): preference within an AS (iBGP only)
- ATOMIC_AGGREGATE (type 6)
- AGGREGATOR (type 7)
- COMMUNITY (type 8, RFC 1997): tags for policy grouping
- MP_REACH_NLRI (type 14, RFC 4760): multiprotocol reachability (IPv6, VPN, etc.)
- MP_UNREACH_NLRI (type 15, RFC 4760): multiprotocol withdrawal

## Decision Process (Route Selection)
BGP selects the "best" path among all candidate routes per prefix:
1. Highest LOCAL_PREF (iBGP; higher is better)
2. Shortest AS_PATH length
3. Lowest ORIGIN (IGP < EGP < INCOMPLETE)
4. Lowest MED (only between routes from same neighboring AS, unless always-compare-med)
5. Prefer eBGP over iBGP
6. Lowest IGP metric to NEXT_HOP
7. Lowest BGP router ID (tie-breaker)

## iBGP vs eBGP
- eBGP: between different ASes; decrements TTL, usually direct link, AS_PATH prepended
- iBGP: within same AS; full mesh required (or route reflectors/confederations); does NOT prepend AS_PATH; LOCAL_PREF is propagated; NEXT_HOP unchanged by default

## Route Reflectors (RFC 4456)
Eliminate iBGP full-mesh requirement. RR re-advertises routes between clients. Uses ORIGINATOR_ID (type 9) and CLUSTER_LIST (type 10) to prevent loops.

## BGP Community (RFC 1997)
Format: AS:value (32-bit). Well-known: NO_EXPORT (0xFFFFFF01), NO_ADVERTISE (0xFFFFFF02), NO_EXPORT_SUBCONFED (0xFFFFFF03). Large Communities (RFC 8092): 96-bit (GlobalAdministrator:LocalData1:LocalData2).

## NOTIFICATION Error Codes
1. Message Header Error
2. OPEN Message Error
3. UPDATE Message Error
4. Hold Timer Expired
5. Finite State Machine Error
6. Cease (subcode 1=MaxPrefixReached, 2=AdministrativeShutdown, 3=PeerDeconfigured, 4=AdministrativeReset, 5=ConnectionRejected, 6=OtherConfigChange, 7=ConnectionCollisionResolution, 8=OutOfResources)

## Blast Radius Concepts
- Session loss: FSM drops to Idle/Active; all routes from that neighbor withdrawn
- Prefix withdrawal: specific NLRI removed from UPDATE; RIB entry deleted
- Route flap: session oscillates; dampening (RFC 2439) may suppress prefix
- Black hole: next-hop becomes unreachable; traffic forwarded to null → silently dropped
- Loop: AS_PATH loop detection prevents iBGP loops; routing loops still possible in data plane
- MED oscillation: inconsistent MED comparison can cause persistent route churn
- Route leak: prefix advertised beyond intended scope (RFC 7908)

## Recursive Next-Hop Resolution
BGP NEXT_HOP must be resolvable in the RIB via an IGP or static route. If the recursive lookup fails, the BGP route is invalid and withdrawn from the FIB. This is the mechanism behind the "blackhole from static route removal" scenario: removing a static route that was the recursive resolver for a BGP next-hop invalidates the BGP prefix.

## Relevant RFCs
- RFC 4271: BGP-4 base
- RFC 4760: Multiprotocol extensions (MP-BGP)
- RFC 4456: Route Reflectors
- RFC 4893: 4-byte AS numbers
- RFC 7908: Route Leaks
- RFC 8092: BGP Large Communities
- RFC 7911: ADD-PATH
- RFC 9234: BGP ONLY_TO_CUSTOMER (OTC)
