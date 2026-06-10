# CenturyLink/Lumen BGP FlowSpec Outage — August 30, 2020

## Summary
On August 30, 2020, Level3/CenturyLink (now Lumen Technologies) suffered a multi-hour backbone outage that disrupted a large fraction of Internet traffic transiting their AS3356/AS3549 network. The root cause was a BGP FlowSpec rule that triggered a bug in a specific router platform, causing routers to restart and withdraw all BGP sessions.

## What Happened

### BGP FlowSpec Background
BGP FlowSpec (RFC 5575) allows distribution of traffic-filtering rules (essentially ACLs) via BGP. Rules specify match criteria (dst prefix, src prefix, protocol, port) and actions (rate-limit, redirect, drop). ISPs use FlowSpec for automated DDoS mitigation — a NOC engineer creates a FlowSpec rule, BGP propagates it to all edge routers automatically.

### The Failure Chain
1. A BGP FlowSpec route was originated (likely intended for DDoS mitigation or traffic engineering)
2. The specific FlowSpec NLRI was malformed or hit an edge case in the FlowSpec implementation on certain router line cards
3. Affected routers encountered a software fault while processing the FlowSpec UPDATE message
4. Routers crashed or entered a state where BGP sessions were torn down
5. With BGP sessions torn down, all routes were withdrawn — both customer routes and transit routes
6. The crash triggered on multiple routers across the backbone simultaneously (because the same FlowSpec UPDATE propagated to all of them)
7. Recovery required either a software restart, manual clearing of the FlowSpec rule, or in some cases hard reboots

### Cascading Effect
- When backbone routers withdrew BGP routes, downstream customers lost connectivity
- Upstream peers saw routes disappear from CenturyLink/Level3 and had to re-route around them
- Because Level3 is a Tier-1 carrier (settlement-free peering with most of the Internet), many paths that relied on Level3 as transit became unavailable
- The simultaneous failure of multiple backbone nodes meant no automatic rerouting was available — the redundant paths also ran through the same Level3 infrastructure

## Blast Radius Analysis
- **D1 (Sessions)**: Massive — all BGP sessions on affected routers torn down. Both eBGP (customer/peer) and iBGP (backbone) sessions affected.
- **D2 (Prefixes)**: All prefixes — customer routes, peer routes, and transit routes — withdrawn simultaneously from affected routers.
- **D3 (Reachability)**: Near-total for traffic transiting Level3. Services hosted on Level3 customers unreachable; transit-dependent paths failed.
- **D5 (Redundancy)**: Eliminated — the failure propagated across the backbone, eliminating intended redundancy.
- **D6 (Filter)**: Indirectly — the FlowSpec rule itself was a filter/policy change that triggered the failure. This is a unique case where a D6 change caused catastrophic D1/D2/D3 impact.

## The FlowSpec Blast-Radius Multiplication Effect
This outage demonstrates a critical blast-radius pattern: **policy changes applied via BGP propagation have a blast radius that scales with the reachability of the BGP UPDATE message.**

A single FlowSpec route originated at one point was propagated (via iBGP and/or eBGP) to every router that accepted the route. The blast radius was not "one router" — it was every router that processed that UPDATE. This is the networked equivalent of a software supply chain attack.

**NetHELM scenario implication**: FlowSpec-triggered failures are a D6 scenario (filter change) that cascades into D1 (session loss) due to platform bug interaction. Pure Batfish cannot model this (platform bugs are not config-derived), but the scenario is valid for testing whether LLMs can reason about propagation scope.

## Key Lessons
1. **FlowSpec has unbounded blast radius in a backbone**: a single FlowSpec announcement reaches all backbone routers simultaneously; a bug in FlowSpec processing causes simultaneous failure
2. **Testing FlowSpec rules is mandatory**: never originate a new FlowSpec NLRI format without testing on a non-production router first
3. **Platform-specific bugs amplify BGP blast radius**: the config change was "correct" (a valid FlowSpec rule); the blast radius came from an implementation bug
4. **Recovery at scale is slow**: when dozens of backbone routers need individual intervention, MTTR can be hours even with large NOC teams

## References
- Cloudflare Radar post-mortem analysis (Aug 2020)
- RIPE stat BGP visibility data for AS3356 (Aug 30, 2020)
- ThousandEyes outage report (Aug 2020)
