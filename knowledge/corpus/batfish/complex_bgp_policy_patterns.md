# Complex BGP Policy Patterns — Advanced Route-Map and Community Design

## Overview
NetConfEval's BGP scenario (bgp_simple) covers only a 2-router eBGP session with no policies. Production BGP deployments involve complex policy chains, community-based routing, inter-AS agreements, and layered route-map structures. This document covers the policy complexity gap.

---

## Policy Architecture: The Four-Layer Model
Enterprise and SP networks typically layer BGP policy as:
1. **Prefix filters (prefix-lists)**: coarse-grained — which prefixes are accepted/advertised
2. **AS-path filters**: which ASes are accepted (peer, transit, customer)
3. **Community-based policy**: fine-grained routing decisions; colored by network role
4. **Attribute manipulation (route-map)**: LOCAL_PREF, MED, weight, next-hop modification

These are applied in sequence at each BGP session. The order matters: a route denied by the prefix-list never reaches the AS-path filter.

---

## Community Design Patterns

### Pattern: RFC 1997 Well-Known Communities
- `NO_EXPORT (0xFFFFFF01)`: do not advertise beyond the local AS
- `NO_ADVERTISE (0xFFFFFF02)`: do not advertise to any peer
- `NO_EXPORT_SUBCONFED (0xFFFFFF03)`: do not export to eBGP peers (keep within confederation)

**Blast radius of missing NO_EXPORT**: a customer route tagged NO_EXPORT is accidentally stripped of the community before export to eBGP peers → customer prefix leaked to Internet (route leak).

### Pattern: BGP Large Community Design (RFC 8092)
Format: `GlobalAdmin:LocalData1:LocalData2` (each 32-bit)
Example design:
```
65001:100:0   = customer route, prefer this path
65001:200:0   = peer route
65001:300:0   = upstream/provider route
65001:0:65001 = do not advertise to AS65001's customers
65001:0:65002 = do not advertise to AS65002
```

**Blast radius pattern**: A community action (`set community 65001:0:65002`) applied to the wrong route-map term propagates to all routes matched by that term, causing those routes to stop being advertised to AS65002.

### Pattern: Community-Based LOCAL_PREF Tiers
```
route-map INBOUND permit 10
 match community COMMUNITY_LP200
 set local-preference 200   ! preferred path
route-map INBOUND permit 20
 match community COMMUNITY_LP100
 set local-preference 100   ! default
route-map INBOUND permit 30
 set local-preference 50    ! least preferred
```
**Blast radius**: if `COMMUNITY_LP200` is matched by more routes than intended (regex too broad in community-list), too many routes get LOCAL_PREF 200 → unexpected traffic engineering; all traffic prefers this path.

---

## Route-Map Complexity Patterns

### Pattern: Permit-Permit-Deny Sequence
```
route-map POLICY permit 10
 match ip address prefix-list SPECIFIC_ROUTES
 set local-preference 200
route-map POLICY permit 20
 match ip address prefix-list GENERAL_ROUTES
 set local-preference 100
route-map POLICY deny 30
 match ip address prefix-list BOGONS
```
**Common mistake**: deny term placed after two permits. Any route matching SPECIFIC_ROUTES or GENERAL_ROUTES is already accepted before reaching the deny. Bogons may pass if they also match GENERAL_ROUTES.
**Correct order**: deny term must come BEFORE the permit that would otherwise match the same routes.

### Pattern: Implicit Deny-All at Route-Map End
IOS: at the end of every route-map, there is an implicit `deny all`. **Any route not explicitly matched is denied.**
- **For inbound**: routes that don't match any term are REJECTED; they don't enter the RIB
- **For outbound**: routes that don't match any term are NOT advertised to the peer

**Blast radius**: Adding a new route-map to a neighbor that previously had no policy → all routes blocked until the route-map has an explicit `permit any` at the end.

**Safe template**:
```
route-map SAFE_POLICY deny 10
 match ip address prefix-list DENY_LIST
route-map SAFE_POLICY permit 20   ! explicit permit-all catchall
```

### Pattern: Match-All (Empty Match)
```
route-map POLICY permit 10
 set local-preference 200
```
An empty `match` clause matches ALL routes. This is often intentional for a catch-all set operation but is frequently written accidentally when the engineer meant to add a `match` clause.

---

## Peer Type Policy Framework
Production networks distinguish peer types and apply different policies:

| Peer Type | Accepted Prefixes | Advertise TO | LOCAL_PREF |
|---|---|---|---|
| Customer (paying) | Customer-owned prefixes only | All peers | 200 |
| Peer (settlement-free) | Peer-owned + customer prefixes | Own + customer only | 100 |
| Upstream/Transit | Full table | Customer only | 50 |

**Implementation**: Each peer has a route-map applying the correct LOCAL_PREF and filtering outbound advertisements:
```
! Only advertise customers and own prefixes to transit (not peer routes):
route-map TO_TRANSIT permit 10
 match ip address prefix-list OWN_PREFIXES
route-map TO_TRANSIT permit 20
 match community CUSTOMER_COMMUNITY
! implicit deny blocks peer routes from being sent to transit
```

**Blast radius of policy inversion**: if TO_TRANSIT accidentally permits peer routes (missing deny), those peer routes are sent to transit → route leak (Telekom Malaysia pattern).

---

## Peer Groups and Template Inheritance
IOS/FRR peer groups apply the same policy to multiple neighbors. Arista EOS uses "peer group" similarly.

**Blast radius**: modifying a peer group policy affects ALL members simultaneously. A route-map change on a peer group with 50 members has 50× the blast radius of the same change on a single neighbor.

**Safe practice**: test policy change on one member before modifying the peer group.

---

## AS_PATH Filtering Patterns

### Regexp Cheat Sheet
- `.*` = any AS path (match all)
- `^$` = empty AS path (originated locally)
- `^65001$` = path consisting only of AS65001
- `_65001_` = 65001 appears anywhere in path (surrounded by separator)
- `^65001_` = path starts with AS65001 (customer routes)
- `_65001$` = path ends with AS65001

**Pitfall**: `_6500_` also matches `_65001_`, `_65003_`, `_650099_` because the underscore matches any separator including none. Use `_6500[^0-9]` or anchor properly.

### Regex Blast Radius Pattern
**Scenario**: Filter intended to deny routes from AS65001: `ip as-path access-list 1 deny _65001_`
**Actual effect if REGEXP too broad**: `_6500_` also denies routes from AS65001, AS65002, AS650033, etc.
**D2**: All routes from unintended matching ASes denied; D3 follows for destinations reachable only via those ASes.

---

## NEXT_HOP Manipulation

### next-hop-self (iBGP)
When PE router R_EDGE advertises eBGP-learned routes to iBGP peers:
- Default: NEXT_HOP unchanged (eBGP peer's address, e.g., 203.0.113.1)
- iBGP peers may not have a route to 203.0.113.1 → route not installed
- **Fix**: `neighbor X.X.X.X next-hop-self` → iBGP peers see R_EDGE's address as next-hop, which they can resolve via IGP

**Blast radius of removing next-hop-self**: iBGP peers lose all routes that had the external next-hop → D2 (all eBGP-learned prefixes) + D3.

### NEXT_HOP Tracking and Scan Timer
BGP verifies next-hop reachability every `bgp next-hop trigger delay N` seconds (default 5s).
**Blast radius implication**: a route may remain in the RIB for up to 5 seconds after its next-hop becomes unreachable. This is a transient black hole window.

---

## Route Refresh and Soft Reset Patterns

### `clear ip bgp X soft in` Blast Radius
- Triggers re-evaluation of all inbound routes against current policy
- Routes that fail the current policy are withdrawn from RIB immediately
- Routes that newly pass (if policy was loosened) are added
- **Zero D1 impact** (session not reset)
- **D2 impact**: potentially large if policy was tightened

### Inbound Soft Reset Without `soft-reconfiguration inbound`
Without `soft-reconfiguration inbound`:
- IOS cannot do `clear ip bgp soft in` without sending ROUTE-REFRESH to the peer (RFC 2918)
- If peer doesn't support ROUTE-REFRESH, soft reset fails → must do hard reset (D1 impact)

---

## Multi-Homed BGP Design — Policy Blast Radius Matrix

| Change | D1 | D2 | D3 | D4 | D7 |
|---|---|---|---|---|---|
| Add inbound route-map (no catchall) | 0 | ALL routes denied | ALL | 0 | 0 |
| Tighten prefix-list (remove entries) | 0 | Removed prefixes | Affected | 0 | 0 |
| Raise LOCAL_PREF on ISP_A | 0 | 0 | 0 | Maybe | Traffic shifts to A |
| Remove next-hop-self on iBGP peer | 0 | All eBGP-learned via this iBGP peer | All | 0 | 0 |
| Enable max-prefix 100 (currently 500 rcvd) | 1 | 500 | All via this peer | 0 | 0 |
| Remove NO_EXPORT from customer route | 0 | 0 | 0 | 0 | Leaked to Internet |
| Change community-list to wider match | 0 | Varies | Varies | Maybe | Traffic shifts |
