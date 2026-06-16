# Blast Radius Scenario Patterns for BGP/OSPF Networks

## Overview
Blast radius measures the set of services, sessions, prefixes, and paths affected by a configuration change. In NetHELM, we measure across 8 dimensions (D1–D8). This document catalogs common scenario patterns.

## Dimension Reference
- D1: BGP sessions lost/gained (count of Established sessions in pre vs. post)
- D2: Prefix reachability lost/gained (RIB entries present in pre but absent in post)
- D3: End-to-end reachability lost (traceroute goes from ACCEPTED to NO_ROUTE or LOOP)
- D4: Waypoint violations (expected transit nodes bypassed or added)
- D5: Redundancy degradation (paths reduced from N to M where M<N)
- D6: Filter policy changes (permits/denies that flip between snapshots)
- D7: Forwarding path changes (next-hop changes even if reachability maintained)
- D8: Scale violations (route/session counts exceed resource limits)

---

## Pattern 1: BGP Neighbor Removal (High Blast Radius)
**Scenario**: Remove a BGP neighbor statement from one router.
**Pre**: `neighbor 10.0.0.2 remote-as 65002` present
**Post**: statement deleted
**Expected blast radius**:
- D1: 1 session lost (the removed neighbor)
- D2: all prefixes learned exclusively via that neighbor are withdrawn
- D3: destinations reachable only via that peer become unreachable
- D5: if peer was only path, redundancy drops to 0

**Validity check**: Batfish models this correctly. Session status changes from ESTABLISHED to NOT_ESTABLISHED.

---

## Pattern 2: Local-Pref Change (Traffic Engineering, Low Safety Impact)
**Scenario**: Increase LOCAL_PREF on inbound routes from one peer.
**Pre**: `set local-preference 100` in route-map
**Post**: `set local-preference 200`
**Expected blast radius**:
- D1: 0 sessions lost (neighbor still up)
- D2: 0 prefixes lost (same prefixes, different preference)
- D7: forwarding path may change if alternate path exists with LOCAL_PREF between 100 and 200
- D4: potential waypoint violation if traffic now takes a different path

**Validity check**: Batfish bgpRib shows different best-path selection post-change.

---

## Pattern 3: Static Route Removal (Recursive Next-Hop Blackhole)
**Scenario**: Remove a static route used as recursive resolver for a BGP next-hop.
**Pre**: `ip route 192.168.100.0/24 Null0` (or a real next-hop used by BGP recursion)
**Post**: static route removed
**Expected blast radius**:
- D2: all BGP prefixes whose NEXT_HOP resolved via this static route become invalid
- D3: destinations behind those prefixes become unreachable (NO_ROUTE disposition)
- D1: BGP session itself may stay ESTABLISHED (TCP remains up); only RIB entries invalidated

**Key insight**: BGP session count (D1) is NOT the right metric here. D2 and D3 catch this.

---

## Pattern 4: Prefix-List Tightening (Filter Change)
**Scenario**: Add a more-specific deny to an inbound prefix-list.
**Pre**: `permit 10.0.0.0/8 le 24`
**Post**: `deny 10.1.0.0/16` added before the permit
**Expected blast radius**:
- D6: subset of 10.1.0.0/16 space now denied (was permitted)
- D2: if those prefixes were exclusively learned via this filtered session, they're withdrawn from RIB
- D3: destinations in 10.1.0.0/16 may become unreachable

**FRR limitation**: Batfish may not parse FRR access-list filters. Use prefix-lists in FRR for testability.

---

## Pattern 5: AS-PATH Prepending (Traffic Engineering)
**Scenario**: Add AS_PATH prepend to make a path less preferred.
**Pre**: no prepend
**Post**: `set as-path prepend 65001 65001 65001`
**Expected blast radius**:
- D1: 0 (session unaffected)
- D7: if an alternate path exists, traffic shifts to it
- D4: potential waypoint violation
- D2: 0 (prefix still reachable via alternate)

---

## Pattern 6: Maximum Prefix Limit (Session Teardown on Overflow)
**Scenario**: Set `maximum-prefix` below current prefix count.
**Pre**: neighbor receives 500 prefixes; no max-prefix configured
**Post**: `neighbor x.x.x.x maximum-prefix 100`
**Expected blast radius**:
- D1: 1 session torn down (NOTIFICATION: Cease/MaxPrefixReached)
- D2: all 500 prefixes withdrawn
- D3: all destinations behind those prefixes unreachable

**Note**: Batfish does NOT model dynamic session teardown from max-prefix. This requires real FRR lab verification. Model shows session status as a function of config, not of runtime prefix counts.

---

## Pattern 7: Route Reflector Client Removal
**Scenario**: Remove a router from RR client list.
**Pre**: `neighbor x.x.x.x route-reflector-client` on RR
**Post**: statement removed
**Expected blast radius**:
- D1: session may stay up (TCP/BGP session not dropped); but RR no longer reflects routes to/from this client
- D2: routes the client was learning via RR reflection become unavailable; routes the client was advertising stop being reflected to other clients
- D3: depends on whether client had alternative paths

---

## Pattern 8: Interface Shutdown (iBGP Next-Hop Resolution Failure)
**Scenario**: Administratively shut an interface that is the loopback used for iBGP peering.
**Pre**: loopback0 = 1.1.1.1/32; iBGP neighbor uses loopback address
**Post**: `shutdown` on loopback0
**Expected blast radius**:
- D1: all iBGP sessions using this loopback as source → NOT_ESTABLISHED
- D2: all prefixes learned via those iBGP sessions withdrawn
- D3: full loss of reachability to destinations only via those peers

**Batfish modeling note**: Batfish infers session status from config topology; shutting an interface removes it from the model correctly.

---

## Pattern 9: Community-Based Policy Change
**Scenario**: Add a community-match deny to a route-map.
**Pre**: route-map permits all routes from peer
**Post**: deny clause added for community 65001:100
**Expected blast radius**:
- D6: routes tagged 65001:100 now denied
- D2: if those prefixes are exclusively from this peer, they're withdrawn
- Scope limited to tagged routes — potentially surgical or broad depending on tagging practice

---

## Pattern 10: OSPF Cost Change (BGP Next-Hop IGP Metric Shift)
**Scenario**: Change OSPF cost on a link, altering IGP shortest path.
**Pre**: link A-B cost 10; link A-C cost 100; BGP next-hop resolved via A-B
**Post**: link A-B cost 200; traffic shifts to A-C
**Expected blast radius**:
- D7: forwarding path changes for prefixes whose BGP next-hop is resolved via affected links
- D4: waypoint violations if A-B was an expected transit
- D1/D2: 0 (reachability maintained, just via different path)

---

## Blast Radius Scoring Formula (NetHELM)
For a given dimension Dx, model output O and ground truth G:
- Precision = |O ∩ G| / |O|  (fraction of model's claimed impacts that are real)
- Recall = |O ∩ G| / |G|  (fraction of real impacts the model caught)
- F1 = 2×P×R / (P+R)

Aggregate score = mean F1 across all non-null dimensions.

## LLM Failure Modes (Observed in Initial Experiments)
1. **Over-counting D1**: LLMs often predict session loss even for changes that don't affect the session (e.g., local-pref changes). Precision for D1 is low.
2. **Under-counting D2**: LLMs rarely enumerate which specific prefixes are lost; they give vague "some prefixes may be lost" responses.
3. **Missing D7**: Forwarding path changes are nearly never predicted.
4. **Missing recursive resolution**: LLMs don't connect static route removal → BGP next-hop invalidation.
5. **Ignoring iBGP split-horizon**: LLMs often miss that iBGP routes are not re-advertised between iBGP peers (without RR).
