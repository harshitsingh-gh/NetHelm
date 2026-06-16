# MED-Driven Quiet Reroute — when a foreign AS's metric edit silently moves your traffic

## Mechanism (blast-radius relevant)

MED (MULTI_EXIT_DISC, RFC 4271 §5.1.4) is the attribute a multi-/dual-homed AS uses
to tell a *single* neighboring AS which entry link to prefer for inbound traffic.
Lower MED wins. It is the canonical inbound-traffic-engineering lever for a customer
dual-homed to one provider over two links.

Key mechanics that make it a *quiet* (D4/D10-only) blast-radius event:

1. **MED is compared only between routes learned from the SAME neighbor AS by
   default** (RFC 4271 §9.1.2.1; FRR's `aspath_cmp_left`). So a customer AS65004
   dual-homed to provider AS65000 over two links has BOTH provider-internal copies
   of its prefix tagged with the same neighbor AS (65004) — MED comparison applies
   with NO `always-compare-med` knob required.
2. **MED is evaluated AFTER weight, LOCAL_PREF, and AS_PATH** (RFC 4271 §9.1.2.2
   step (c)/(d)). It only decides the best path when LOCAL_PREF is equalized across
   the two egresses and AS_PATH lengths are equal. If LP is *not* equalized, a MED
   edit is a complete no-op — the decision terminates earlier.
3. **A MED change is an attribute UPDATE, not a session event.** The BGP FSM
   (RFC 4271 §8) leaves Established only on NOTIFICATION, hold-timer expiry, or TCP
   teardown — never on a policy/attribute change. So a MED edit produces **zero
   D1** (no session loss). Common LLM error: predicting a session drop here.
4. The prefix stays BEST in every RIB (only its chosen next-hop changes) → **D2=∅**;
   the dual-homed host is still delivered via the other link → **D3=∅, D7=∅**; a
   strict MED gap yields a single best path → **D5=∅** (no ECMP to lose).
   The ONLY casualty is *which entry link / which internal waypoint the traffic
   transits* → **D4 (waypoint) + D10 (intent invariant)**.

## Why this is a distinct CAUSE from the more-specific leak

The 2019 Cloudflare/Verizon leak (see `cloudflare_bgp_leak_jun2019.md`) is a
longest-prefix-match event: a NEW more-specific /24 is injected and LPM pulls
traffic onto it. The MED reroute injects **no new prefix and no more-specific** —
the same /24 stays best everywhere; only its *attribute ranking* between two
existing same-AS copies flips, at the MED step of the decision process. Same damage
signature (quiet D4), structurally different cause.

A second distinguishing axis is **locus of cause**: the breaking diff can live
entirely in a *foreign* administrative domain (the dual-homed customer's own
outbound route-map). The provider's own configs are byte-identical, yet the
provider's internal best path — and the inspection/scrubbing waypoint it was
supposed to transit — silently moves. "Someone else's change broke my invariant"
is a real and underappreciated class of blast-radius event.

## Real-world grounding

- **Standard practice, documented.** A dual-homed customer setting MED on its
  outbound advertisements so its single upstream prefers one entry link is textbook
  inbound TE. See AWS's own guidance for active/passive BGP over Direct Connect
  (customer sets MED to make one DX link primary):
  https://aws.amazon.com/blogs/networking-and-content-delivery/creating-active-passive-bgp-connections-over-aws-direct-connect/
  and NSRC's "Multiple Dual-Homed Customers" curriculum:
  https://learn.nsrc.org/bgp/multiple_dual_homed_customers
  (Caveat for realism: in the *multi-transit* case many ISPs strip/ignore customer
  MED — this mechanism's honored-MED assumption holds for the *single-provider
  dual-homed* topology, which is exactly the topology modeled.)

- **MED's operational treachery is well documented.** Ivan Pepelnjak's "BGP MED
  Saga" catalogs how easy it is to get MED wrong — including a Priority-1 TAC case
  from "someone deciding to set MED only on the backup link" and vendor-default
  divergence (IOS-XR/JUNOS behave as if `deterministic-med` were on; IOS/IOS-XE do
  not): https://blog.ipspace.net/2023/11/bgp-med-saga/

- **Order-dependence / persistent oscillation is RFC-documented.** Without
  `bgp deterministic-med`, best-path among same-neighbor-AS routes with differing
  MEDs can depend on the order routes were received, and MED + route-reflection or
  confederations can cause *persistent route oscillation* (RFC 3345, "BGP Persistent
  Route Oscillation Condition," Aug 2002):
  https://www.rfc-editor.org/rfc/rfc3345
  Cisco's note on why `deterministic-med` exists and how it differs from
  `always-compare-med`:
  https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/16046-bgp-med.html

## Determinism caveat for the oracle (load-bearing)

The order-dependence above is precisely why a *live-FRR* validation config of this
mechanism MUST carry `bgp deterministic-med` to guarantee a single stable best path.
But that exact line is NOT in Batfish's FRR grammar (it returns
PARTIALLY_UNRECOGNIZED), and Batfish is deterministic by construction regardless.
Resolution: keep `deterministic-med` only in the live-FRR validation config and
strip it from the Batfish oracle snapshot; document the idiomaticity gap. This is
why the mechanism is graded BUILD_V1.1, not a clean V1.

## Blast-radius mapping

- **D1 = ∅** — attribute update, no session reset.
- **D2 = ∅** — prefix stays best in every RIB.
- **D3 = ∅, D7 = ∅** — dual-homed host still delivered via the other link.
- **D5 = ∅** — strict MED gap → single best path, no ECMP set to lose.
- **D4 = fires** — traffic stops transiting the mandated inspection/scrubbing node.
- **D10 = fires** — "traffic to X MUST transit Y" invariant broken.

This is the pure-quiet signature: nothing lost, nothing withdrawn, full reachability
preserved — only the mandated waypoint silently bypassed.

## References
- RFC 4271 §5.1.4 (MULTI_EXIT_DISC), §8 (FSM), §9.1.2 (decision process):
  https://www.rfc-editor.org/rfc/rfc4271
- RFC 3345 (BGP Persistent Route Oscillation Condition):
  https://www.rfc-editor.org/rfc/rfc3345
- ipSpace "The BGP MED Saga": https://blog.ipspace.net/2023/11/bgp-med-saga/
- Cisco deterministic-med vs always-compare-med:
  https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/16046-bgp-med.html
- AWS active/passive over Direct Connect (customer-set MED):
  https://aws.amazon.com/blogs/networking-and-content-delivery/creating-active-passive-bgp-connections-over-aws-direct-connect/
