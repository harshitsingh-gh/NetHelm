# Telekom Malaysia BGP Route Leak — June 12, 2015

## Summary
On June 12, 2015, Telekom Malaysia (TM, AS4788) leaked approximately 179,000 BGP prefixes to Level3 Communications via a peering point in Hong Kong. Level3 (AS3356) accepted and propagated these routes globally, causing widespread Internet disruption for around 1–2 hours. This is one of the largest route leaks by prefix count in Internet history.

## What Happened

### The Route Leak
Telekom Malaysia had a BGP peering session with Level3 in Hong Kong. TM's network was also connected to many other ASes (as a large regional ISP). 

At some point, TM began announcing routes learned from their other peers and upstreams back to Level3 — routes that TM was not authorized to advertise to Level3. This is the classic route leak pattern defined in RFC 7908: TM was propagating routes learned from one provider/peer to another provider/peer without the originating ASes' permission.

The routes TM leaked included prefixes belonging to major networks globally. The leak count was ~179,000 routes — a significant fraction of the global BGP table at the time (~512,000 routes).

### Level3's Acceptance
Level3 should have filtered TM's announcements to only accept routes for IP space TM legitimately originated or was authorized to transit. Level3 did not have adequate filtering in place for TM.

Once Level3 accepted these routes and propagated them through their backbone (one of the largest Tier-1 carriers), the fake routes were visible globally.

### Traffic Impact
- Routers globally that received both the legitimate route and TM's leaked route had to choose: based on AS_PATH length and other attributes, some traffic was misdirected to TM's network
- TM's network could not handle the traffic surge — it was not provisioned to be a transit provider for the world's Internet traffic
- Packet loss and high latency were the primary symptoms for affected traffic flows
- The impact was uneven: networks whose traffic happened to prefer TM's path (based on BGP path selection) were affected; others saw no impact

## Blast Radius Analysis
- **D1 (Sessions)**: Zero — no sessions dropped
- **D2 (Prefixes)**: Counterintuitive — from a reachability standpoint, most prefixes were still "reachable" via legitimate paths. The issue was traffic taking the wrong path. Some prefixes may have effectively become unreachable due to congestion at TM.
- **D3 (Reachability)**: Partial and traffic-dependent. Not a total blackout.
- **D4 (Waypoint)**: This is the primary dimension — 179,000 prefixes had their traffic unexpectedly flowing through TM (a waypoint violation for every affected flow).
- **D7 (Forwarding path)**: Changed for all traffic that preferred TM's leaked routes.
- **D5 (Redundancy)**: In some cases, the legitimate path still existed but was hidden by the more-preferred (shorter AS_PATH or similar) leaked route.

## Why This Is the Canonical D4 (Waypoint) Outage at Scale
The Pakistan/YouTube 2008 outage was a single-prefix total blackout. The TM 2015 outage demonstrates **large-scale waypoint violation without blackout**: traffic was partially routed, but via incorrect paths.

This is operationally difficult because:
- Monitoring shows sessions up, prefixes present, reachability nominally OK
- The problem is only visible in traceroutes and latency measurements
- BGP-level metrics (session count, prefix count) give no signal

**This is the exact failure mode that D4 (waypoint) and D7 (forwarding path) dimensions are designed to detect.**

## Scale of the Problem
179,000 leaked routes × N traffic flows per route = effectively every major Internet service was at risk. The fact that this caused only moderate disruption (not total Internet failure) is because:
1. Not all traffic preferred TM's leaked path — many preferred existing paths
2. TM's network could handle some traffic before becoming congested
3. Level3 withdrew the routes after being notified (within ~1-2 hours)

## The IRR/RPKI Prevention Argument
- IRR filtering would have prevented this if Level3 had checked TM's AS-SET against each announced prefix
- RPKI would not have directly prevented this (route origin was valid — the original origin ASes owned the prefixes); what would help is BGP OTC (RFC 9234: Only to Customer) / BGP Role attributes that mark a session as "customer" and prevent propagating customer routes back to providers

## References
- BGPmon analysis of TM route leak (June 2015)
- RFC 7908: Problem Definition and Classification of BGP Route Leaks
- Renesys/Dyn blog: "How Pakistanís Internet Went Dark" (general BGP hijack analysis)
- CAIDA routing data for AS4788 (June 12, 2015)
