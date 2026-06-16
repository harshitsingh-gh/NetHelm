# Load-Bearing Prepend / MED Removed During "Cleanup" — A Quiet Waypoint Bypass

## Why a dedicated file
This is a high-value, **quiet-half** blast-radius class: a config "cleanup" that
deletes an AS-path prepend (or a `set metric`/MED) which *looks* vestigial but was
the only tie-breaker keeping a bypass path **less preferred** than a mandated
waypoint path. Removing it equalizes the two paths; best-path selection then falls
through to a lower RFC 4271 §9.1.2.2 step and silently selects the bypass. **Nothing
drops** — no session, no prefix, no reachability, no redundancy, no blackhole. Traffic
still arrives at every destination. It simply stops transiting the mandated node
(scrubber / firewall / DPI / lawful-intercept tap / mandated transit AS). This is the
D4 (waypoint) + D10 (intent) signature with D1/D2/D3/D5/D7 all empty.

## The mechanism (RFC 4271 §9.1.2.2 decision order)
1. Highest LOCAL_PREF — both paths tie (operator did NOT use LP for this control).
2. **Shortest AS_PATH** — PRE: the bypass egress carries `set as-path prepend <self>
   <self>`, deliberately lengthening it so the waypoint path wins here. The diff
   DELETES the prepend → AS_PATH lengths **equalize** → selection falls through.
3. Lowest ORIGIN, 4. Lowest MED, 5. eBGP > iBGP, 6. Lowest IGP metric to NEXT_HOP,
   7. Lowest BGP router-ID / received-from — POST: with AS-paths equal, the winner is
   decided at a lower step. In the FRR/Batfish model this resolves on the
   originator/`received-from` comparison, a **pure function of the pinned snapshot**
   (NOT arrival order), so it is deterministic across runs.

## Mechanics corrections (caught empirically; do NOT repeat the proposal's error)
- `bgp bestpath compare-routerid` is **NOT parsed by Batfish's FRR (CUMULUS_
  CONCATENATED) model** — emitting it yields PARTIALLY_UNRECOGNIZED. It is also
  unnecessary: the FRR model's BgpRib comparator does NOT use arrival-order tie-break
  by default, so the equalized tie resolves deterministically via the static
  best-path comparator chain. OMIT it.
- The post-equalization winner does **not** track router-id the way the naive story
  claims; it tracks the fixed per-instance relative numbering of the two upstreams
  (compareReceivedFrom / originator). Generator rule (load-bearing): place the brace
  (prepend) on the **lower-numbered** upstream and mandate the **higher-numbered**
  upstream as the waypoint, so removal deterministically flips toward the
  lower-numbered node. The naive "prepend-on-alt, waypoint=way" build is a NO-OP.
- This is the structural **dual** of an explicit LOCAL_PREF bump on the waypoint path
  (the lp_waypoint scenario, caught at 1.00 recall). Here NO diff line signals a
  preference change — a prepend is *deleted* — so the "deleting unused config is safe"
  prior actively suppresses suspicion. That prior is the reasoning trap under test.

## Blast radius (get this right in the oracle)
- **D1 = 0**: a route-map clause/prepend deletion re-evaluates Adj-RIB-In; no FSM
  event, no session reset. (Common LLM error: claiming the session drops. It does not.)
- **D2 = 0**: the prefix stays BEST in the observer's RIB pre and post; only AS_PATH
  length changes. Both paths present throughout.
- **D3 = 0**: the bypass delivers — trace terminates ACCEPTED via the bypass post.
- **D5 = 0**: `maximum-paths` default 1 → exactly one strict BEST in each snapshot.
- **D7 = 0**: no null/blackhole/loop trace.
- **D4 = 1, D10 = 1**: traffic no longer transits the mandated waypoint; intent broken.

## Real-world grounding
- **Operational class — "dormant config removed turns out load-bearing"** is well
  documented: TravisCI's age-based image-cleanup job deleted stable base VM images;
  GitHub Copilot's partner resource-cleanup job removed essential infra; a 2026
  WireGuard outage traced to a recursive rule "lying dormant for 14 months." These
  are the same anti-pattern (Chesterton's Fence in config), differing only in object.
  - danluu/post-mortems collection: https://github.com/danluu/post-mortems
- **Prepend is the brace that holds traffic engineering / inbound path** — and is
  routinely the thing operators remove when it "looks like it does nothing," not
  realizing upstream LP or a tie-break depends on it.
  - https://www.pinglabz.com/bgp-as-path-prepending/ (when prepending works/doesn't;
    upstream LOCAL_PREF can nullify a customer prepend)
  - https://bgplabs.net/policy/7-prepend/ (prepend to influence inbound path)
- **Security framing — routing-layer change quietly bypasses the inspection node**,
  invisible to firewall/SIEM logs because the path changed, not the perimeter:
  BGP path changes move traffic "before it hits the firewall," at the architectural
  layer below SIEM visibility.
  - https://saptanglabs.com/the-great-internet-heist-why-bgp-hijacking-is-the-ultimate-infrastructure-invisible-man/
- Confidence: the BGP-prepend-cleanup-causes-silent-reroute specific instance is a
  **war story / analogous** (no single named public post-mortem — quiet reroutes
  don't make headlines because nothing breaks). The broader cleanup-of-load-bearing-
  config class and the routing-bypasses-inspection class are **documented**.

## References
- [RFC 4271 — BGP-4 §9.1.2.2 Decision Process](https://www.rfc-editor.org/rfc/rfc4271.html)
- [RFC 7908 — BGP Route Leaks](https://www.rfc-editor.org/rfc/rfc7908.html)
- danluu/post-mortems: https://github.com/danluu/post-mortems
