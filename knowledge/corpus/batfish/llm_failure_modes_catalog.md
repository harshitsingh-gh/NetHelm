# LLM Failure Modes on Blast Radius Tasks — Observed and Predicted

## Overview
This document catalogs observed and predicted failure modes of LLMs (GPT-4o, Claude, Gemini) when reasoning about network configuration blast radius. This is the ground truth for what NetHELM is testing.

---

## Observed Failures (From Initial NetHELM Experiments)

### Failure Mode F1: Session-Count Overcount (D1 Inflation)
**Description**: LLMs predict BGP session loss for changes that do NOT cause session loss.
**Examples that trigger this**:
- LOCAL_PREF change: LLM says "sessions may be disrupted" → WRONG (no session impact)
- MED change: LLM says "session will reset to apply new MED" → WRONG
- Community tag change: LLM says "BGP will re-establish to advertise new community" → WRONG

**Why LLMs get this wrong**: Training data contains many descriptions of "BGP changes affect routing" without distinguishing between attribute changes (no session impact) and neighbor/policy changes (may or may not affect sessions). The LLM over-generalizes.

**Correct knowledge**: Only the following cause BGP session teardown:
1. `no neighbor X` (neighbor removal)
2. `neighbor X remote-as Y` change (AS number mismatch)
3. `neighbor X shutdown`
4. `neighbor X password X` change (authentication failure)
5. Hard `clear ip bgp X.X.X.X`
6. Interface or loopback carrying the TCP session goes down
7. Hold timer expiry
8. Maximum prefix exceeded (if warning-only not set)
9. Platform bug triggered by specific attribute (rare)

### Failure Mode F2: Prefix-Count Undercount (D2 Deflation)
**Description**: LLMs say "some prefixes may be affected" without enumerating which ones.
**Examples**:
- "Some routes from this neighbor may be withdrawn" (vague)
- "Certain prefixes that depend on this session will be unavailable" (correct but not specific)

**What's needed**: The LLM should enumerate (or describe the set of) prefixes affected. For a neighbor removal, the answer should be: "all prefixes learned exclusively from neighbor X" — not just "some prefixes."

**Scoring implication**: A vague answer that cannot be evaluated for precision/recall should score poorly. NetHELM requires structured output for D2.

### Failure Mode F3: Missing Recursive Resolution Chain
**Description**: LLMs fail to trace the chain: static route removal → IGP route invalidation → BGP next-hop failure → prefix withdrawal.

**Typical LLM response**: "Removing a static route affects connectivity to that prefix."
**Correct response**: "Removing static route 10.0.0.0/24 removes the IGP path to next-hop 10.0.0.1, which is the recursive resolver for BGP prefix 192.168.1.0/24 on R1. Therefore, 192.168.1.0/24 is withdrawn from R1's FIB even though the BGP session remains ESTABLISHED."

**Pattern**: The deeper the chain (static → OSPF → BGP → customer traffic), the more likely the LLM is to stop at step 1 and miss the downstream effects.

### Failure Mode F4: Ignoring iBGP Split-Horizon Rule
**Description**: LLMs assume routes learned via iBGP are re-advertised to other iBGP peers (they are NOT without a Route Reflector).

**Example scenario**: 4-router iBGP full mesh. Remove one full-mesh session (R1-R3). LLM says "R3 can still learn routes via R2." 

**Correct analysis**: In full-mesh iBGP, each router DOES learn routes from every other router via direct iBGP sessions. Removing R1-R3 session means R3 cannot learn routes originated by R1 directly. R2 receives R1's routes but does NOT re-advertise them to R3 (iBGP split-horizon). So R3 loses R1's routes completely.

**Exception**: If R2 is configured as a Route Reflector with both R1 and R3 as clients, R2 WILL re-advertise (that's the RR purpose). LLMs often confuse full-mesh and RR topologies.

### Failure Mode F5: Over-Predicting D3 (Reachability Loss)
**Description**: LLMs predict complete reachability loss for changes that only affect a subset of paths.
**Example**: LOCAL_PREF change on one of two upstreams. LLM says "connectivity to the Internet is lost." 
**Correct**: connectivity is maintained via the other upstream; traffic shifts (D7) but D3 = 0.

**Root cause**: LLMs conflate "route is affected" with "destination is unreachable." Reachability depends on whether ANY valid path remains, not just whether the specific path is affected.

### Failure Mode F6: Bidirectional Session Confusion
**Description**: LLM claims removing a `neighbor` statement on R1 also removes the session on R2.
**Correct**: In BGP, the session is bidirectional (TCP connection). Removing `neighbor R2` from R1's config causes R1 to tear down the TCP session. R2 detects the TCP RST or timeout and also drops the session. Both sides lose the session, but R2 did not initiate the removal.

**Where this matters for D2**: If the LLM reasons "R2 also removes its neighbor config" it will incorrectly predict R2 loses routes it was advertising TO R1. R2 loses routes it was LEARNING FROM R1. The directionality matters for understanding which prefixes are lost where.

### Failure Mode F7: Missing Anycast Impact
**Description**: LLMs do not understand that withdrawing an Anycast prefix from one PoP causes traffic shift, not total loss.

**Correct understanding**: An Anycast prefix (e.g., Cloudflare's 1.1.1.1/32) announced from 200 PoPs globally. Withdrawing from 10 PoPs: clients nearest those 10 PoPs are affected; clients nearest other PoPs are unaffected. D3 impact is proportional to traffic share of affected PoPs.

### Failure Mode F8: No Understanding of RPKI Invalid Impact
**Description**: LLMs treat routes the same regardless of RPKI validation state. They do not predict that an RPKI-invalid route will be dropped by ROV-implementing routers.
**Correct**: RPKI ROV → INVALID route dropped at routers performing ROV → effectively the same as a session teardown for prefixes covered by that ROA.

---

## Predicted Failure Modes (Not Yet Tested)

### F9: MED Oscillation Not Recognized as Blast Radius
LLMs will likely say "MED change affects traffic engineering" but not identify it as a D7 (forwarding path change) or recognize the oscillation risk when both `always-compare-med` and multiple upstreams are involved.

### F10: RTBH Prefix-Length Misidentification
LLMs will likely not distinguish between `/32` RTBH (surgical, minimal blast radius) and `/24` RTBH (256 addresses, high blast radius). They will say "null route injected" without quantifying the scope.

### F11: Conditional Advertisement Dependency Not Traced
LLMs will likely not connect the exist-map check to the conditional advertisement — they will not predict that withdrawing PREFIX_B (the exist-map trigger) also withdraws PREFIX_A (the conditionally advertised prefix).

### F12: VRF Route Leak Not Identified as D4
LLMs may identify that the wrong routes are now in a VRF but fail to connect this to traffic misdirection (D4) — the security implication of customer traffic crossing VRF boundaries.

---

## Scoring Calibration Based on Failure Modes

| Scenario type | Expected LLM score | Primary failure mode |
|---|---|---|
| Neighbor removal (simple) | HIGH (~0.7) | F6 (directionality confusion) |
| LOCAL_PREF change | MEDIUM (~0.4) | F1 (session over-count) |
| Static route → recursive BGP | LOW (~0.2) | F3 (missing chain) |
| RR client removal | LOW (~0.2) | F4 (split-horizon miss) |
| RTBH /24 blast radius | LOW (~0.2) | F10 (prefix-length scope) |
| MED oscillation | VERY LOW (~0.1) | F9 (not recognized) |
| Anycast PoP withdrawal | LOW (~0.2) | F7 (proportional impact missed) |
| Aggregate masking blackhole | VERY LOW (~0.1) | Novel scenario |

## How These Failure Modes Inform NetHELM Design
1. Scenarios should be chosen to expose the full range of failure modes — easy scenarios (F1 simple detection) to hard (F3, F4 multi-step chains)
2. Rubric must require STRUCTURED output (named prefixes, session counts) not prose ("some routes affected")
3. Grader must penalize F1 (false positives on D1) equally to F3 (false negatives on D2)
4. A model that avoids F1 by never predicting D1 losses will have high D1 precision but zero D1 recall — grader must report both
