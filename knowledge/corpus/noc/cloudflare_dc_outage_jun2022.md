# Cloudflare 19-Datacenter Outage — June 21, 2022

## Summary
On June 21, 2022, Cloudflare accidentally took down 19 of its data centers for approximately 1 hour during a network infrastructure change intended to improve the architecture of their backbone. The outage affected a significant portion of Cloudflare's global traffic. The root cause was an incorrect BGP configuration change that caused routers in the affected data centers to withdraw their routes.

## Background: Cloudflare's Network Architecture Change
Cloudflare was in the process of converting their backbone network from a multi-protocol architecture to a more consistent design. The change involved deploying a new network architecture to a set of data centers simultaneously as part of a planned maintenance rollout.

## What Happened

### The Configuration Change
During the change deployment, a BGP configuration was pushed that introduced an incorrect routing policy. Specifically, the new configuration caused backbone routers to prefer routes that were invalid or withdraw announcements for the IPs that Cloudflare serves traffic from.

The key failure was: the new routing policy removed the prefixes that Cloudflare's Anycast IPs were announced from in those 19 data centers. When those announcements were withdrawn, clients could no longer route to Cloudflare's edge nodes in those locations.

### Propagation
- The configuration was deployed simultaneously to all 19 data centers as part of a batch rollout
- Each data center's routers withdrew their BGP announcements for Cloudflare's Anycast prefixes
- Traffic that would have been served by those 19 data centers had no available endpoint
- Globally distributed clients attempting to reach Cloudflare-proxied services received no response or connection timeouts
- Services relying on Cloudflare's DDoS protection, CDN, and DNS (including 1.1.1.1) were affected

### Rollback Difficulty
The same network change that caused the outage also affected the out-of-band management paths. This is a recurring theme in network outages: the change that breaks the network also breaks the tools used to fix it.

Recovery required:
1. Identifying the specific config change that caused the issue
2. Manually reverting the config on affected routers
3. Staged restoration to verify each data center came back cleanly

## Blast Radius Analysis
- **D1 (Sessions)**: All eBGP sessions from affected data centers to upstream peers/transit providers withdrew (from the peer's perspective, Cloudflare stopped announcing from those locations)
- **D2 (Prefixes)**: Cloudflare's Anycast prefixes (e.g., 104.16.0.0/13, 104.24.0.0/14, 1.1.1.1/32, 1.0.0.1/32) withdrawn from 19 data centers' announcements. Globally, the prefixes still existed (from the remaining 81+ data centers not affected), but with degraded coverage.
- **D3 (Reachability)**: Clients whose closest Cloudflare data center was one of the 19 affected lost reachability entirely. Clients whose traffic was topologically nearest to other data centers were unaffected.
- **D4 (Waypoint)**: For clients that lost their closest PoP, traffic either went to a more distant Cloudflare PoP (if BGP re-convergence allowed) or failed entirely.
- **D5 (Redundancy)**: Severely degraded — 19 of ~200+ PoPs lost simultaneously. The redundancy of Anycast normally provides global resilience; losing a batch simultaneously degrades it proportionally.

## The Anycast BGP Blast-Radius Pattern
This outage illustrates a specific and important blast-radius pattern for Anycast architectures:

**Anycast prefix withdrawal = loss of PoP coverage for all clients topologically nearest to that PoP.**

Unlike unicast prefixes (where withdrawal = total unreachability), Anycast prefix withdrawal from a subset of PoPs means:
- Clients nearest the withdrawn PoPs lose their best path
- Some may fail over to a more distant PoP (higher latency, potentially overloaded)
- Some may fail entirely if no other PoP is reachable via their ISP's routing

This is a partial D3 impact — quantifiable only if you know the traffic distribution across PoPs.

## Why Batch Deployment Is High Risk
Cloudflare, like Facebook in 2021, deployed a change simultaneously across many sites. The blast radius of a simultaneous deployment equals the sum of blast radii of all individual deployments — there is no isolation.

**NetHELM scenario implication**: This is a D2+D4 scenario class — Anycast prefix withdrawal causing waypoint violations. Batfish can model this if you represent each data center's BGP config separately.

## Key Lessons
1. **Batch-deploy to canary first**: change one data center, verify traffic before rolling to all 19
2. **Out-of-band management must be isolated from the change**: if your management path uses the same BGP infrastructure you're changing, you can't fix it remotely when it breaks
3. **Anycast withdrawal has a non-linear blast radius**: withdrawing 19/200 PoPs doesn't affect 9.5% of traffic — it affects 100% of clients whose closest PoP was one of those 19

## References
- Cloudflare blog: "Cloudflare outage on June 21, 2022" (published same day)
- Cloudflare Radar BGP data for affected prefixes
