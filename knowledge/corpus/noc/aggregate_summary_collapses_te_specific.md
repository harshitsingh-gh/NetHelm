# Aggregate summary-only Collapses a Steering More-Specific (Inverse-LPM Collapse)

## Summary
A traffic-engineering / security design pins steered traffic onto a **more-specific**
prefix (e.g. a /25 or /24) whose best path transits a mandated waypoint (a DDoS
scrubbing center, a firewall/DPI node, an LI tap, a mandated transit AS). A covering
aggregate (the /24 or /22) also exists on a different egress as the normal fallback.
Longest-prefix-match (LPM) at observers selects the more-specific, so traffic transits
the waypoint.

A later, benign-looking **table-hygiene change** — `aggregate-address <cover> summary-only`
(or a `suppress-map`) — **suppresses advertisement of the contributing more-specific**.
Observers stop hearing it; LPM falls back to the covering aggregate, whose best path
egresses on the off-waypoint side. **Reachability is fully preserved by the aggregate**
(no host loses the destination), but the mandated waypoint is silently bypassed.

This is the *inverse polarity* of the classic more-specific route leak: the leak ADDS a
more-specific to PULL traffic onto an unintended path (Cloudflare/Verizon 2019); this
REMOVES a more-specific so LPM falls BACK to a coarser path. Same LPM machinery, opposite
direction. Same blast-radius signature as the leak's quiet half: D4 (waypoint) + D10
(intent invariant) only, with reachability intact.

## Why This Is a Real Production Trap

### More-specifics are deliberately used to steer traffic
BGP-based DDoS scrubbing routinely works by announcing a **more-specific** prefix
(commonly a /24, down to /25 for sub-allocations) to divert traffic into the scrubbing
center; the covering aggregate continues to be the normal/clean path. In "always-on"
mode the more-specific is permanently advertised and the aggregate is the off-scrubber
fallback; in on-demand mode it is announced on attack and withdrawn afterward.
- FastNetMon: "FastNetMon announces a more specific prefix (for example, a /24 in IPv4)
  to divert traffic globally" and "can automatically withdraw the diversion announcement,
  restoring normal routing." (https://fastnetmon.com/ddos-scrubbing-centre-diversion/)
- Gcore / Radware / Alibaba Anti-DDoS all document the same more-specific-diversion +
  GRE-return-path pattern. (https://gcore.com/learning/bgp-gre-facilitate-ddos ;
  https://support.radware.com/app/answers/answer_view/a_id/1018551/ ;
  https://www.alibabacloud.com/help/en/anti-ddos/anti-ddos-origin/user-guide/bgp-diversion-mode-for-data-centers-outside-alibaba-cloud)
- "you either advertise a more specific prefix (e.g. /24), either you prepend or stop
  advertising the prefix to your regular upstream providers."

The same more-specific-steers / aggregate-is-fallback pattern is used for plain traffic
engineering (pulling a subnet's inbound onto a preferred ingress) and for hairpinning a
subnet through an inspection node.

### summary-only suppresses contributors — by design
`aggregate-address <prefix> summary-only` suppresses advertisement of ALL contributing
more-specifics. Operators who need to keep advertising *some* of them must explicitly
use `suppress-map` / `unsuppress-map` (Cisco) or equivalent — the very existence of
leak/suppress-map proves that summary-only otherwise kills the more-specifics:
- Cisco: "The summary-only keyword suppresses all the more specific routes of an
  aggregate address from being advertised."
  (https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/5441-aggregation.html)
- "Some traffic engineering designs require leaking routes ... done at the process by
  explicitly stating the prefixes to suppress, or on a neighbor level by indicating
  which prefixes should not be suppressed."
  (https://www.noction.com/knowledge-base/bgp-route-aggregation)

### Summarization always loses information
"Route summarization (regardless of the routing protocol) always results in information
loss and potential suboptimal paths or black holes." When the lost information IS the
steering more-specific, the result is a silent waypoint bypass with reachability intact.
(https://blog.ipspace.net/2024/03/ospf-split-areas-summarization/)

### The operational trap
The operator running the cleanup typically does NOT know the more-specific was load-
bearing for steering/inspection. The diff reads as pure table hygiene ("the /24 already
covers it, drop the redundant specific"). No alarm fires: sessions stay up, the space
stays in the RIB as the aggregate, every destination still answers. The only thing that
changed is which prefix LPM matches — and therefore which egress, and therefore whether
the mandated waypoint is traversed. This is exactly the class a session/prefix/reach
grader scores as a clean pass.

## Blast-Radius Mapping (D1-D10)
- **D1 sessions**: empty. No neighbor change.
- **D2 prefixes**: empty **for the watched covering route** (the /24). The steering
  more-specific (/25) is *summarized, not blackholed* — its address space stays reachable
  via the aggregate. (KB `maintenances_that_caused_outages.md` Type 5 Reaggregation:
  aggregate covers same space => D2=0, D3=0.) NOTE: if the steering /25 is itself in the
  D2 watch set it WILL fire D2 (it genuinely leaves the RIB), which makes the scenario
  "loud." For a pure-quiet instance the steering more-specific must be EXCLUDED from the
  watch set — the policy invariant, not the prefix, is what's being tested.
- **D3 reachability**: empty. The aggregate delivers; every destination still answers.
- **D4 waypoint**: VIOLATED. Pre: traces transit the mandated node. Post: traces egress
  via the off-waypoint path.
- **D5 redundancy/ECMP**: empty. The aggregate pre-existed as a single dormant fallback
  (one path); promoting it to active removes no co-installed member, so no ECMP churn.
- **D7 forwarding anomaly**: empty **iff** the surviving aggregate is backed by a
  genuinely-delivering path (never Null0/discard). If the aggregate is a discard
  summary, this goes LOUD on D7/D3 (blackhole). Pure-quiet requires a live aggregate.
- **D10 intent invariant**: VIOLATED (te_pin: the steering /25 present pre, gone post;
  waypoint invariant: must transit inspection node).

Signature = **D4 + D10 only**; full reachability preserved => quiet half.

## Distinct From the More-Specific Leak (Cloudflare/Verizon 2019)
The leak (see `cloudflare_bgp_leak_jun2019.md`) ADDS a more-specific from a third party
to PULL traffic; LPM at the observer prefers the longer leaked prefix and the leaker
delivers, so reachability survives but the path is wrong. This mechanism REMOVES a
more-specific (via local summary-only/suppress-map on the legitimate egress), so LPM
falls BACK to a pre-existing local aggregate on the un-inspected path. Opposite
specificity direction, opposite operator intent (tidying vs. optimizing/leaking), and
the bypass path is the operator's own legitimate aggregate, not a third party's
announcement. Same observable damage signature (quiet D4+D10), different root cause.

## Confidence
- Mechanism (summary-only suppresses contributors; LPM falls back to aggregate):
  DOCUMENTED (Cisco/Noction/FRR behavior).
- More-specific-as-steering-for-scrubbing/TE: DOCUMENTED (FastNetMon/Radware/Gcore/Alibaba).
- A single named public post-mortem where summary-only cleanup specifically bypassed a
  scrubber/waypoint: NOT located in public write-ups (scrubbing-path misconfigurations
  are rarely published). The composite is ANALOGOUS/WAR-STORY at the incident level but
  every constituent mechanism is documented. Treat the specific composite as analogous;
  do not assert it as a named outage.

## Sources
- Cisco, "Understand Route Aggregation in BGP" — summary-only suppresses all more-specifics.
  https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/5441-aggregation.html
- Noction, "BGP Route Aggregation" — TE leak/suppress-map exists because summary-only kills specifics.
  https://www.noction.com/knowledge-base/bgp-route-aggregation
- FastNetMon, "DDoS Scrubbing Centre Diversion" — more-specific /24 diversion + withdraw.
  https://fastnetmon.com/ddos-scrubbing-centre-diversion/
- Gcore, "How BGP and GRE Tunneling Can Facilitate DDoS Protection."
  https://gcore.com/learning/bgp-gre-facilitate-ddos
- Radware, "BGP Configuration for Routing-Based Diversion."
  https://support.radware.com/app/answers/answer_view/a_id/1018551/
- ipSpace.net, "OSPF Summarization and Split Areas" — summarization loses information => suboptimal/blackhole.
  https://blog.ipspace.net/2024/03/ospf-split-areas-summarization/
- KB: `maintenances_that_caused_outages.md` Type 5 (Reaggregation: aggregate covers space => D2=0/D3=0).
- KB: `cloudflare_bgp_leak_jun2019.md` (the inverse-polarity anchor).
