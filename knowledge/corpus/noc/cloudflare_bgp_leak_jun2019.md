# Cloudflare Global Outage — June 24, 2019 (Route Leak)

## Summary
On June 24, 2019, Cloudflare lost approximately 15% of its traffic for ~18 minutes due to a BGP route leak originating from a small ISP in Pennsylvania (Allegheny Technologies). The leak caused Verizon to propagate more-specific routes for Cloudflare's prefixes through a third-party AS, attracting traffic away from Cloudflare's intended paths.

## What Happened

### The Route Leak
1. Allegheny Technologies (AS396531), a small networks company, was using Noction's BGP Optimizer — a tool that learns routes and re-announces them as more-specific /24 prefixes to optimize internal routing.
2. The tool accidentally leaked these more-specific prefixes to their upstream provider, DQE Communications (AS10282).
3. DQE should have filtered these (route leak prevention), but did not have proper route filters.
4. DQE's upstream, Verizon (AS701), accepted and propagated these more-specific routes globally.
5. The more-specific /24 routes (Cloudflare's broader /21s or /20s were replaced by /24 sub-prefixes) were preferred by BGP's longest-prefix-match rule.
6. Traffic destined for Cloudflare flowed through Allegheny/DQE instead, causing congestion and packet loss.

### Why More-Specifics Are Dangerous
BGP always prefers the most-specific matching route. If Cloudflare announces `1.1.1.0/22` and a route leak announces `1.1.1.0/24`, all routers receiving both will forward to `/24` first. This is the mechanism.

### Scope
- Cloudflare traffic globally affected (15% loss for 18 min)
- Other networks' prefixes in the leak: ~368 routes, including Cloudflare, Amazon, and others
- Amazon, Linode, and others also transiently affected

## Failure in the Ecosystem
Three parties failed:
1. **Noction BGP Optimizer** at Allegheny: leaked routes it should have kept internal
2. **DQE**: no outbound route filters; accepted and propagated routes it should not have
3. **Verizon**: no ingress filters on customer routes; propagated clearly bogus routes globally

## Mitigations (RPKI, BGPSEC, IRR)
- **RPKI ROA (Resource Public Key Infrastructure, Route Origin Authorization)**: cryptographic attestation that AS X is authorized to announce prefix P. Verizon (and others) checking RPKI would have dropped the leak because Allegheny had no ROA for Cloudflare's space.
- **IRR (Internet Routing Registry)**: route-level filters based on AS-set declarations in RIPE, ARIN, APNIC databases. Requires manual maintenance.
- **MANRS (Mutually Agreed Norms for Routing Security)**: industry framework requiring ISPs to implement filtering, anti-spoofing, and coordination.

## Blast Radius Analysis
- **D1 (Sessions)**: No sessions lost — route leak doesn't tear down sessions, it misdirects traffic.
- **D2 (Prefixes)**: Technically prefixes were still reachable via correct path, but effective reachability was degraded.
- **D3 (Reachability)**: 15% traffic loss — partial D3 impact (not total blackout).
- **D4 (Waypoint)**: This is the classic D4 scenario — traffic traversed an unintended waypoint (Allegheny/DQE instead of Cloudflare edge).
- **D5 (Redundancy)**: Unaffected at routing level; the leak was a path-selection problem, not path elimination.

## Key Lessons for NetHELM
1. **Route leaks manifest as D4 (waypoint) violations, not D1 or D2**: A session-count or prefix-count metric would not detect this outage at all.
2. **More-specific hijack**: The attack surface for route hijacking is via longer prefixes — a critical scenario class for blast radius testing.
3. **Transit acceptance**: The lesson about Verizon propagating is relevant to "what should a transit AS filter?" — a knowledge-base question type.
4. **Batfish detectability**: If you had Verizon's configs, Batfish would show the more-specific routes in the RIB and the wrong forwarding path — classic D4 and D7 scenario.

## Related Incidents
- **Pakistan Telecom / YouTube (Feb 2008)**: AS path hijack; YouTube unreachable for 2 hours globally.
- **China Telecom (Apr 2010)**: ~15% of global routes briefly hijacked via more-specific announcements.
- **Telekom Malaysia (Jun 2015)**: 179,000 prefixes leaked; major disruption.
