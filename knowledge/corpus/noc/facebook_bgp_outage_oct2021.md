# Facebook/Meta Global Outage — October 4, 2021

## Summary
On October 4, 2021, Facebook, Instagram, WhatsApp, and Messenger were unreachable for approximately 6 hours (roughly 15:39–21:30 UTC). The root cause was a configuration change to the backbone routers that carried BGP routing information between data centers.

## What Happened (Technical)

### The Change
A routine BGP maintenance command, issued during routine network infrastructure maintenance, accidentally took down all the connections in the backbone network and disconnected Facebook's data centers globally.

Specifically, a command intended to assess the capacity of the global backbone inadvertently disrupted the entire backbone routing. This caused all BGP routes to Facebook's edge and data center infrastructure to be withdrawn.

### BGP Withdrawal Cascade
1. The backbone network changes caused the BGP peers between Facebook's data centers to go down.
2. With no backbone routes, Facebook's edge servers could not reach the data centers. Edge routers withdrew their BGP routes to Facebook's prefix space from the global Internet.
3. Facebook's AS (AS32934) stopped announcing ~140,000+ IP prefixes to the Internet.
4. DNS servers also went offline (they were in Facebook's address space). Facebook's authoritative DNS for `facebook.com`, `instagram.com`, `whatsapp.com` became unreachable.
5. Because DNS was down, even internal tooling that used internal FQDNs failed.

### DNS Amplification of Impact
- DNSSEC validation failed globally for facebook.com once the authoritative nameservers withdrew.
- The sudden absence of DNS responses caused a flood of retry queries — ~22× normal DNS query rates globally, impacting adjacent DNS infrastructure.
- External recursive resolvers (8.8.8.8, 1.1.1.1) received SERVFAIL for facebook.com queries.

### Recovery Difficulty
Facebook engineers could not use their normal remote access tools because those tools also relied on the internal network that was down. Physical access to data centers was required. Multi-factor authentication systems were also unavailable because they relied on the same infrastructure.

Recovery required:
1. Physical travel to data centers
2. Manual intervention on backbone routers (console access)
3. Careful, staged restoration to avoid overload — bringing everything back at once risked cascade failures from reconnection storms

## Blast Radius Analysis
- **D1 (BGP sessions)**: Essentially all eBGP sessions from Facebook's edge routers to transit/peer ASes dropped when Facebook stopped announcing prefixes. The sessions themselves may have stayed TCP-established, but the routes were withdrawn.
- **D2 (Prefixes)**: ~140,000 prefixes withdrawn from global routing tables.
- **D3 (Reachability)**: 100% of Facebook services unreachable from the Internet.
- **D5 (Redundancy)**: Complete — no redundant path existed because the change affected the backbone itself, which all edge connections depend on.

## Key Lessons for NetHELM
1. **BGP session count (D1) is insufficient**: The sessions may stay up but routes be withdrawn. D2 (prefix count) is the more direct measure.
2. **Config changes on backbone routers have unbounded blast radius**: A change affecting the backbone propagates to all dependent services (DNS, auth, monitoring).
3. **Recovery tooling depends on the network**: If the network change breaks the tools used to fix it, blast radius extends to recovery time.
4. **Batfish simulation**: This outage would be partially detectable — Batfish would show BGP prefixes withdrawn from edge routers and traceroutes returning NO_ROUTE for facebook.com space. The backbone misconfiguration itself might not be directly modeled without the internal backbone configs.

## References
- Facebook Engineering Blog (Nov 2021): "More details about the October 4 outage"
- Cloudflare Radar blog: "Understanding how Facebook disappeared from the Internet"
- BGP data: RIPE RIS, RouteViews, CAIDA BGP stream
