# IGP-Metric Hot-Potato Quiet Reroute — an OSPF/IS-IS cost edit silently moves the BGP egress (and the mandated waypoint)

## Mechanism (blast-radius relevant)

When two iBGP paths to the same destination are tied on every BGP attribute that is
compared earlier in the decision process — weight, LOCAL_PREF, AS_PATH length,
ORIGIN, MED, and eBGP-vs-iBGP type — BGP best-path falls through to **RFC 4271
§9.1.2.2 step (e): lowest IGP metric to the BGP NEXT_HOP** (the "closest egress" /
hot-potato tiebreak; this is FRR best-path step ~8 and Batfish `BgpRib.comparePreference`
step `getIgpCostToNextHopIp`). The egress a router chooses is therefore decided by
the *IGP cost to reach the next-hop*, not by any BGP knob.

**Consequence:** a single intradomain cost edit — `ip ospf cost N` on a transit link,
or an IS-IS metric retune, framed as routine capacity / latency / TE / maintenance-drain
work — can re-resolve the unchanged BGP next-hop and flip which egress wins, **without
touching one BGP attribute.** If the egress that loses was the one co-located with a
mandated inspection / scrubbing / DPI / LI-tap / firewall node, traffic silently stops
transiting that waypoint while still being delivered to the destination.

This is the "hot-potato routing" interaction between intradomain and interdomain
routing. It is one of the best-documented IGP↔BGP coupling hazards in the operational
literature (see grounding below).

## Why this is a *quiet* (D4/D10-only) blast-radius event

1. **D1 = ∅ — no session loss.** An OSPF/IS-IS cost change never touches the BGP FSM.
   RFC 4271 §8: an Established session leaves only on NOTIFICATION, hold-timer expiry,
   or TCP teardown. A cost-only edit (no MTU/area/network-type/passive change) also
   keeps the OSPF adjacency Full. Common LLM error: predicting a session drop because
   "an interface/protocol line changed."
2. **D2 = ∅ — nothing withdrawn.** The destination prefix stays BEST in every RIB; mask
   and all BGP attributes are unchanged. Only the *resolved next-hop / chosen egress*
   moves. (Note: the winning path's NEXT_HOP **value** does change — it becomes the
   winning egress's own link address — but the prefix is never withdrawn and reachability
   is preserved; the oracle grades transit, not next-hop identity.)
3. **D3 = ∅, D7 = ∅ — full reachability.** The alternate egress delivers the prefix
   exactly as the original egress did. No blackhole, no loop. Hot-potato *reroutes*
   the egress; it does not drop the traffic (Agarwal ICNP'05, Teixeira SIGMETRICS'04
   both measure this as an egress shift, not a loss).
4. **D5 = ∅ — single best path, IF AND ONLY IF a strict IGP-metric gap holds in BOTH
   snapshots.** This is the load-bearing purity constraint. An *exact equal-cost IGP
   tie* installs BOTH next-hops (ECMP width 2) → D5 FIRES and D4 degrades to a mixed
   transit. `maximum-paths 1` does NOT save you in the steady-state model — only a
   strict resolved-metric gap does. The generator MUST read back the resolved OSPF
   metrics and assert a strict (non-equal) gap pre AND post.
5. **D4 fires** — all traces stop transiting the mandated egress/waypoint.
   **D10 fires** — the "traffic to X MUST transit Y" invariant breaks.

Pure-quiet signature: nothing lost, withdrawn, blackholed, looped, or de-redundant;
traffic still arrives; only the mandated waypoint is silently bypassed.

## Why this is a distinct CAUSE from the more-specific leak and from MED reroute

- **vs. more-specific leak (`leak_ms_reroute`, Cloudflare/Verizon 2019):** that is a
  longest-prefix-match event at the *prefix-specificity* layer — a NEW more-specific
  /25 wins LPM. Here **no new prefix and no more-specific is ever originated**; the same
  prefix with identical mask and identical BGP attributes stays best on both candidate
  paths. The decisive change lives **one layer down**, in recursive next-hop resolution:
  the *IGP cost* used to resolve an unchanged next-hop.
- **vs. MED reroute (`med_driven_quiet_reroute`):** MED decides at RFC 4271 step (d),
  *before* the IGP tiebreak, and the breaking edit is a BGP attribute. Here every BGP
  attribute (including MED) is tied, the decision reaches step (e), and **the breaking
  edit is not in BGP at all — it is in the IGP.** This is the only quiet mechanism whose
  decisive diff line is in a *different protocol* from BGP.
- **vs. the explicit `lp_waypoint`** (a direct LOCAL_PREF bump on the waypoint path,
  already caught by all 8 models at 1.00 recall): that diff literally sets a BGP
  attribute on the waypoint path. Here there is **zero BGP surface** — no
  neighbor/route-map/network/LOCAL_PREF/AS-path/prefix-list/shutdown line changes.

## Why a model misses it (the subtlety)

To predict the bypass the model must chain a cross-protocol inference of ≥4 steps:
`OSPF cost edit → SPF cost to the BGP NEXT_HOP changes → best-path step-(e) IGP
tiebreak flips (which presupposes recognizing the two iBGP paths are attribute-tied so
best-path even REACHES step (e)) → egress changes → mandated waypoint bypassed`. The
diff contains no BGP token at all, so a model pattern-matching on "BGP attribute
changed?" sees nothing. This is the documented LLM failure mode for >2-step causal
chains. Realism is high: IGP cost retunes for capacity/latency/TE/maintenance drains
are among the most common, most-automated, lowest-ceremony changes an operator makes —
and the egress-shift side effect is exactly what the literature below warns is routinely
overlooked.

## Real-world grounding (peer-reviewed, measured on operational tier-1 backbones)

This is NOT a contrived mechanism. The IGP-cost→BGP-egress-shift coupling is a named,
measured, well-cited operational phenomenon ("hot-potato routing dynamics").

- **Feamster, Borkenhagen, Rexford — "Guidelines for Interdomain Traffic Engineering,"
  ACM SIGCOMM CCR 33(5), Oct 2003.** Characterizes routing/traffic data from a large
  **tier-1 IP backbone (AT&T)**. Defines the decision-process step "Lowest IGP metric:
  Prefer routes with the smallest intradomain (IGP) metric to reach the next hop … This
  enables each router to select its 'closest' exit point," and warns that the search
  space of "changes to BGP policies and IGP weights is extremely large" and that
  operators can make changes with "an unpredictable effect on the flow of traffic."
  http://ccr.sigcomm.org/archive/2003/v33n5/ccr-v33n5-4-feamster.pdf

- **Teixeira, Shaikh, Griffin, Rexford — "Dynamics of Hot-Potato Routing in IP
  Networks," ACM SIGMETRICS, Jun 2004.** Measured on the **AT&T backbone**. Findings:
  hot-potato routing is a significant source of BGP updates; the BGP egress change can
  lag 60s+ behind the intradomain (IGP) event; the triggered path changes have a nearly
  uniform distribution across destination prefixes. "When choosing between multiple
  equally-good BGP routes, a router selects the one with the closest egress point, based
  on the intradomain path cost. Under such hot-potato routing, an intradomain event can
  trigger BGP routing changes."
  https://dl.acm.org/doi/abs/10.1145/1005686.1005723

- **Agarwal, Nucci, Bhattacharyya — "Measuring the Shared Fate of IGP Engineering and
  Interdomain Traffic," IEEE ICNP 2005.** Measured on the **Sprint backbone** (Sprint
  ATL co-author). Direct, quantified statement of the exact mechanism:
  - "Hot-potato routing occurs when there are multiple egresses to reach a destination.
    BGP inside that AS will pick the egress point which is 'closest' - i.e., has least
    IS-IS or OSPF cost from the traffic ingress point."
  - Worked example: "if due to IGP engineering the cheapest IS-IS cost from Miami to San
    Francisco goes to 55, then BGP will change the egress to Seattle for this destination"
    — a single link-cost edit re-homing the egress, exactly this mechanism.
  - Scale: a typical iBGP table on a Sprint router has ~150,000 prefixes; for **~60% of
    prefixes there are 2+ candidate egresses where IGP cost is the determining factor** —
    i.e. the majority of the table is exposed to this. "as much as 25% of traffic to a
    neighboring AS can shift the exit point" from local IGP tuning, and ignoring the
    interaction left link-utilization metrics "sub-optimal by as much as 20%."
  - Traffic is **rerouted, not dropped** — the study measures egress *shifts*, with
    reachability preserved (the paper's entire concern is congestion/SLA on the new path,
    not loss).
  https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icnp05.pdf

- **KB cross-reference:** `noc/maintenances_that_caused_outages.md` already records the
  pattern row "OSPF cost change | None (L2) | New forwarding paths | Next-hop path change
  | D7+D4" — i.e. a cost edit shifts forwarding without an L2/session event. In the
  *quiet* topology (strict-gap, delivered alternate egress) the D7 column collapses and
  only D4+D10 remain.

**War-story confidence note for the publication:** the *named, public post-mortem* of a
single OSPF cost edit silently bypassing an inspection waypoint is hard to source — such
events are usually caught internally as "why is this flow no longer hitting the scrubber"
tickets, not published outages. What IS documented and peer-reviewed (above) is the
underlying mechanism, measured on AT&T and Sprint, affecting the majority of the prefix
table. Grounding confidence for the mechanism = **documented**; the specific
waypoint-bypass framing is **analogous** (the egress-shift is documented; the
inspection-node-on-the-egress invariant is the operational overlay we add). Do not claim
a named outage; claim the measured mechanism, which is exactly what these three papers
establish.

## Blast-radius mapping

- **D1 = ∅** — IGP cost edit; no BGP FSM event, OSPF adjacency stays Full.
- **D2 = ∅** — prefix stays best in every RIB; nothing withdrawn.
- **D3 = ∅, D7 = ∅** — alternate egress delivers; no blackhole/loop.
- **D5 = ∅** — strict resolved-IGP-metric gap pre AND post → single best path. (HAZARD:
  an exact equal-cost tie fires D5 and pollutes D4 — the generator must assert the strict
  gap, not rely on `maximum-paths 1`.)
- **D4 = fires** — all traces stop transiting the mandated egress/waypoint.
- **D10 = fires** — "traffic to X MUST transit Y" invariant broken.

## Generator / oracle constraints (load-bearing)

1. Baseline MUST be an **OSPF (or IS-IS) underlay with recursive next-hop resolution and
   ZERO static resolvers** — a static resolver (as in the flat `lp_waypoint` topology)
   masks the IGP cost and makes the mechanism inexpressible. Reuse the proven `ospf_core6`
   idiom (`ip ospf area 0`, `ip ospf network point-to-point`, passive `lo`, no `ip route`).
2. The generator MUST read back the **resolved** OSPF/IS-IS metric to each candidate
   egress next-hop and ASSERT (a) a strict (non-equal) gap PRE and POST, and (b) exactly
   one installed best path each snapshot. SPF arithmetic accumulates per-hop outgoing-
   interface cost, so a single `ip ospf cost` edit does NOT simply set the path cost — a
   mis-parameterized seed can silently land on a tie (D5 pollution) or fail to flip
   (vacuous, no-D4 instance). Same assert-discipline `generator_lp` already uses.
3. Include the **`no_op` calibration control**: a cost edit that does NOT cross the gap
   (way still wins) — prose-indistinguishable from the bypass, ground truth completely
   empty. This is what proves a passing model reasoned about the cross-protocol chain
   rather than pattern-matching on "an OSPF cost line changed."

## References
- RFC 4271 §9.1.2.2 step (e) (lowest IGP metric to NEXT_HOP), §8 (FSM):
  https://www.rfc-editor.org/rfc/rfc4271
- Feamster, Borkenhagen, Rexford, "Guidelines for Interdomain Traffic Engineering,"
  ACM SIGCOMM CCR 33(5), Oct 2003:
  http://ccr.sigcomm.org/archive/2003/v33n5/ccr-v33n5-4-feamster.pdf
- Teixeira, Shaikh, Griffin, Rexford, "Dynamics of Hot-Potato Routing in IP Networks,"
  ACM SIGMETRICS, Jun 2004: https://dl.acm.org/doi/abs/10.1145/1005686.1005723
- Agarwal, Nucci, Bhattacharyya, "Measuring the Shared Fate of IGP Engineering and
  Interdomain Traffic," IEEE ICNP 2005:
  https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icnp05.pdf
