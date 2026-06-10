# Anycast Catchment Shift — Reachability Looks Fine, a Region Goes Dark or Overloads

## Why a dedicated file
Anycast (one prefix announced from many PoPs; BGP delivers each client to its
nearest instance) is how every large CDN / DNS / edge platform scales. The
blast-radius trap: **withdrawing or de-preferring an anycast origin at one PoP does
NOT remove the prefix from the Internet** — the prefix is still announced elsewhere,
so a naive prefix/reachability check shows the service "up." The real blast is the
**catchment shift**: clients formerly served by that PoP are re-homed to the
*next-nearest* instance. That shift is either (a) a latency/capacity event (the
remaining PoPs absorb the load) or, in the worst case, (b) a region going dark if the
withdrawn PoP was the **sole origin** reachable for that catchment. Dimensions per
`../batfish/blast_radius_patterns.md` (D1–D8). DC-anycast capacity mechanics:
`../dc/dc_summarization_ecmp_pitfalls.md` (Part B.5).

## The mechanism
Anycast routing "delivers that packet to the nearest instance based on BGP path
selection" — nearest by **AS-path length / BGP best-path, not geography**
([Cloudflare — Anycast](https://www.cloudflare.com/learning/cdn/glossary/anycast-network/)).
A client's *catchment* = the set of sources whose BGP best-path lands them on a given
instance. Catchment boundaries are an emergent property of every transit/peer AS's
own best-path decision — the operator does not control them directly.

Two operations that shift catchment:
1. **Full withdrawal of the origin at a PoP** (drain, maintenance, health-check
   failure). BGP withdraws the announcement at that PoP; every transit AS recomputes
   and re-homes the affected catchment to the next-nearest instance. "When an edge
   node becomes unavailable, BGP routes are withdrawn and traffic automatically
   shifts to the next nearest PoP."
   [Cloudflare — anycast primer](https://blog.cloudflare.com/a-brief-anycast-primer/)
2. **De-preference / weighted withdrawal** (AS-path prepend, lower MED/community at
   one PoP) — shifts a *fraction* of the catchment gradually rather than a binary
   cut-over. Modern CDNs use "weighted Anycast withdrawal — reducing the BGP
   community preference rather than fully withdrawing — so traffic gradually shifts to
   neighboring PoPs." (operational practice; see search grounding.)

## Real incident grounding
**Cloudflare 1.1.1.1 Resolver outage, July 14 2025** — the textbook *sole-origin /
full-withdrawal* anycast failure. A dormant config error (introduced June 6) tied the
resolver prefixes to a pre-production service; a July 14 topology refresh triggered it
and the resolver prefixes were, in Cloudflare's words, *"reduced from all locations
down to a single, offline location."* `1.1.1.0/24`, `1.0.0.0/24`,
`2606:4700:4700::/48` and others were withdrawn from all production data centers
simultaneously. Impact: *"The majority of 1.1.1.1 users globally were affected"* for
62 minutes (21:52–22:54 UTC) — **traffic did not shift to a healthy PoP, it went dark**
because there was no remaining healthy origin to catch it.
[Cloudflare — 1.1.1.1 incident, July 14 2025](https://blog.cloudflare.com/cloudflare-1-1-1-1-incident-on-july-14-2025/)

This is the worst-case end of the spectrum (withdrawal from *all* PoPs → no
next-nearest exists). The general catchment-shift class is the partial version:
withdraw at ONE PoP and the next-nearest absorbs the catchment (latency/capacity
blast), unless that one PoP was the only origin reachable for some region — which then
goes dark while the *global* prefix still looks present.

Contrast for grounding: the DNS root-server system is explicitly engineered so this
trap is survivable — "If an instance goes down, its BGP announcement is withdrawn and
traffic routes to the next-nearest instance," and the root system "has never suffered
a complete outage" precisely because no catchment is sole-origin.
[dnslab — root servers](https://www.dnslab.dev/learn/docs/infrastructure/root-servers)

## The change → trap → blast
**Change:** withdraw / prepend / lower-pref an anycast origin at one PoP (a drain, a
maintenance, a "cleanup" of an announcement, a health-check-driven withdrawal).

**Trap:** the anycast prefix is STILL globally present and STILL reachable in a
traceroute from most vantage points → a prefix-presence (D2) or single-vantage
reachability (D3) check passes clean. The damage is per-catchment and capacity/latency.

**Blast set:**
- **D1 = 0** — peering sessions unchanged (the change is an announcement/attribute
  edit, not a session teardown). Common LLM error: claiming sessions drop.
- **D2 (global) = 0** — the prefix remains present from other PoPs. **D2 lies**, same
  signature as the summarization blackhole.
- **D7 (forwarding/catchment shift)** — THE PRIMARY DIMENSION. The catchment that
  homed to the drained PoP now lands on the next-nearest instance: a different
  forwarding path / different serving site for a large set of sources.
- **D5 (redundancy)** — for the affected region, origin diversity drops N→N−1; if the
  drained PoP was the only reachable origin for some catchment, redundancy → 0 and
  that region **goes dark** (the Cloudflare-style sole-origin case) even though the
  prefix is globally up.
- **Effective D8 (capacity)** — the next-nearest PoP(s) now absorb the drained PoP's
  load. "Remaining nodes may absorb 2× load, causing latency climbs and timeouts."
  A capacity cliff, not a reachability loss — tests whether a model reasons about load,
  not just presence.

## Batfish modellability
**PARTIAL — the honest answer.** Batfish is a single-AS / provided-config simulator;
it does NOT know the *external* Internet's per-source best-path, which is what defines
real catchment. So Batfish cannot tell you which client ASes re-home where.
- **What it CAN grade:** within a modeled topology (e.g., the operator's own backbone
  with multiple internal anycast origins, or a multi-PoP fabric whose configs you
  hold), diff the **per-ingress next-hop / chosen-origin** pre/post — the catchment
  shift becomes a deterministic forwarding-set diff (D7), and a region with zero
  remaining origin shows NO_ROUTE (D5→0 / D3). The sole-origin "goes dark" case is
  fully gradeable when all relevant origins are in-model.
- **What it CANNOT:** the global Internet catchment, real load distribution, the 2×
  capacity figure, and the hash/instance selection. Those are LIVE/measurement
  properties.
- **Workaround:** build the scenario *inside* a modeled multi-origin topology and
  score (1) does any ingress lose its only origin (D5→0 / dark) and (2) which
  ingresses change serving origin (D7). Annotate per-PoP capacity as a spec to score
  the effective-D8 overload threshold (count-vs-limit, like the Rogers D8 pattern in
  `rogers_canada_outage_jul2022.md`).

## Why this is NOT redundant
- Distinct from neighbor removal / withdrawal (Pattern 1): there the prefix
  *disappears* and D2/D3 fire globally. Here the prefix **stays globally present** and
  the blast is a *catchment/capacity* shift — the inverse signature.
- Distinct from the ECMP/anycast-hotspot collapse in `dc_summarization_ecmp_pitfalls.md`
  Part B.5 (that is intra-fabric add-path/multipath collapse homing all traffic to one
  *instance via one next-hop*). This class is *inter-PoP catchment* re-homing across a
  WAN/Internet boundary. Related amplifier, different layer — cross-ref, don't merge.

## Key lessons
1. "The anycast prefix is still announced" does NOT mean every region is still served.
2. Draining one PoP is a capacity/latency event for the rest — model the load, not
   just reachability.
3. Sole-origin catchments are the killers: a withdrawal that looks like 1 PoP of N can
   be 100% for the region that had only that PoP (Cloudflare 1.1.1.1, in the limit
   where N=all).

## References
- [Cloudflare — 1.1.1.1 Resolver incident, July 14 2025](https://blog.cloudflare.com/cloudflare-1-1-1-1-incident-on-july-14-2025/)
- [Cloudflare — What is Anycast?](https://www.cloudflare.com/learning/cdn/glossary/anycast-network/)
- [Cloudflare — A brief anycast primer](https://blog.cloudflare.com/a-brief-anycast-primer/)
- [DNS root servers — anycast resilience](https://www.dnslab.dev/learn/docs/infrastructure/root-servers)
- [Catchpoint — DNS Anycast concepts](https://www.catchpoint.com/dns-monitoring/dns-anycast)
- Cross-refs (internal): `../dc/dc_summarization_ecmp_pitfalls.md` (Part B.5 anycast
  capacity), `./rogers_canada_outage_jul2022.md` (D8 count-vs-limit pattern),
  `../batfish/blast_radius_patterns.md`.
