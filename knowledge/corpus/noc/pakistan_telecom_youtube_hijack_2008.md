# Pakistan Telecom / YouTube BGP Hijack — February 24, 2008

## Summary
On February 24, 2008, Pakistan Telecommunications Company Ltd (PTCL, AS17557) accidentally hijacked YouTube's IP space globally, making YouTube unreachable worldwide for approximately 2 hours. This is one of the most-studied BGP security incidents and the canonical example of the route hijack blast-radius pattern.

## Background
The Pakistani government ordered ISPs to block YouTube (due to objectionable content). Pakistan Telecom attempted to implement this by announcing a more-specific BGP route to null-route YouTube's traffic within Pakistan.

## What Happened

### The Intended Action
Pakistan Telecom wanted to block `208.65.153.0/24` (a YouTube prefix, within YouTube's announced `208.65.152.0/22`) **only within Pakistan**. They announced the more-specific `/24` route with a next-hop pointing to a black-hole (discard) interface — internally, this was a correct and functional block.

### The Accidental Global Leak
- PTCL's upstream provider was PCCW Global (AS3491), a major Hong Kong-based carrier
- PTCL had a peering session with PCCW. PCCW accepted the more-specific `/24` route from PTCL.
- PCCW then propagated this route to their global BGP peers and customers
- Because `208.65.153.0/24` was more specific than YouTube's `208.65.152.0/22`, every BGP router that received both routes preferred the `/24` (longest-prefix match)
- Globally, traffic destined for YouTube's addresses in that `/24` was directed to PTCL's network, then to the null-route → dropped

### Timeline
- ~18:48 UTC: PTCL originates more-specific route
- ~18:50 UTC: Route propagates globally via PCCW
- ~18:50–20:50 UTC: YouTube globally unreachable for 2+ hours
- ~20:50 UTC: PCCW withdraws the route after being notified; YouTube recovers

### Why PCCW Should Have Filtered
PCCW should have had outbound route filters preventing PTCL from advertising routes for IP space that PTCL did not own. The correct filter would check: "is this prefix registered in an IRR (Internet Routing Registry) as belonging to PTCL or their customers?" It was not — YouTube's space belongs to Google/YouTube. The filter was missing.

## Blast Radius Analysis
- **D1 (Sessions)**: Zero — no BGP sessions were dropped. This outage caused zero session disruption.
- **D2 (Prefixes)**: Zero lost (YouTube's prefix still existed in routing tables) — but the "winning" route pointed to a black hole. The prefix was "present but wrong."
- **D3 (Reachability)**: ~100% for YouTube (effectively total for the hijacked /24 space)
- **D4 (Waypoint)**: This is primarily a D4 scenario — traffic was forced through an unintended waypoint (PTCL's network) en route to a black hole
- **D7 (Forwarding path)**: Complete change — all traffic for the /24 went to PTCL instead of YouTube's data centers

## The More-Specific Hijack Pattern
This is the canonical **D4/D7 scenario** and the most important BGP blast-radius scenario class:

**Precondition**: Target announces `P/N`. Attacker (accidentally or maliciously) announces `P/N+k` (same prefix, longer mask).
**Effect**: BGP longest-prefix-match causes global traffic shift to attacker.
**Detection**: Session/prefix counts look normal. D1=0, D2=0. Only D4 (waypoint) and D7 (forwarding path) show the problem.
**Severity**: 100% traffic loss for affected prefix range, zero warning signs in session-count metrics.

**Why this is critical for LLM evaluation**: A naive model that only evaluates D1 (session count) would score this as "no blast radius." The correct answer is maximum D4/D7 impact. This tests whether the LLM understands that BGP blast radius is not just about sessions — forwarding correctness is equally critical.

## Batfish Modellability
If you have configs for PCCW's routers (hypothetically), Batfish would show:
- `bgpRib` on PCCW node: two routes for 208.65.153.0/24 — one from PTCL (fraudulent), one learned elsewhere
- BGP best-path selection: PTCL's route wins (assuming AS path length or other attributes favor it)
- `traceroute` from any external node to 208.65.153.x: goes to PTCL, then NO_ROUTE or LOOP

**In a simulated NetHELM scenario** (frr_square equivalent with a hijack): you can implement this by adding a more-specific announcement to one router and asking the LLM to predict the forwarding impact.

## RPKI Would Have Prevented This
A valid ROA for 208.65.152.0/22 by Google/YouTube with max-length /24 would allow Google to announce that prefix. But PTCL announcing it from AS17557 would be an RPKI-invalid route. Any router doing RPKI ROV (Route Origin Validation) would drop PTCL's announcement.

In 2008, RPKI did not exist operationally. As of 2024, ~50% of Internet prefixes have ROAs, and ~30% of ASes perform ROV — the same attack would be partially mitigated today.

## References
- RIPE routing data: AS17557 prefix announcements, Feb 24, 2008
- Renesys (now Dyn) blog post: "Pakistan Hijacks YouTube" (Feb 2008)
- Cisco blog: "When Pakistan Hijacked the Internet" 
- RFC 7908: Problem Definition and Classification of BGP Route Leaks
