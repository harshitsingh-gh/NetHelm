# DC Route Summarization & ECMP/Multipath Pitfalls (Deep Dive)

## Why a dedicated file
Two DC-specific failure classes are (a) the most *counter-intuitive* — they invert
enterprise/WAN "best practices" — and (b) among the most *Batfish-modellable*, which
makes them prime NetHELM scenario material. Both share a signature: **D1=0, D2 looks
fine, but D3/D5/D7 are broken** — the change "looks safe and isn't." This file
develops the mechanics so scenario authors get the blast set EXACTLY right. Dimensions
are D1–D8 per `../batfish/blast_radius_patterns.md`. General fabric design context:
`./hyperscaler_fabric_design.md`. Incident mappings: `./hyperscaler_dc_failure_modes.md`.

> **Two gradeable sub-variants of the summarization blackhole (don't conflate):**
> (1) the *conditional* form (Part A.3/A.4 below) — summary added, then a LATER link
> failure blackholes; D2=0 at change time. (2) the *single-snapshot* form implemented
> by the `clos_summary` scenario — a spine already lacks a DIRECT path to the server
> leaf (it only had it indirectly via the leaves), and the same summarization change
> SUPPRESSES the specific toward the leaves, severing that indirect path; D2 fires
> immediately (the specific leaves the RIBs while the /8 masks it). Same root cause
> ("a spine sources a summary for a prefix it can't actually reach"), graded as one
> pre/post delta. The verified `clos_summary` ground truth is the authority.

---

## Part A — Summarization blackholes in a Clos

### A.1 The rule, verbatim
RFC 7938 §5.2.3: "Summarizing subnets in a Clos topology results in route
black-holing under a single link failure (e.g., between Tier 2 and Tier 3 devices),
and hence must be avoided."
[RFC 7938 §5.2.3](https://datatracker.ietf.org/doc/html/rfc7938)

The structural reason (RFC 7938 §3.2.2): "Tier 1 switches have exactly one path to
every server in this topology." A summary hides the loss of that one path.

### A.2 The mechanism, step by step (the blast set scenario authors must reproduce)
Topology: leaves L1..Lk, spines S1..Sn, every leaf connected to every spine. Suppose
an operator configures spines (or an aggregation tier) to advertise a **summary**
(or a default) toward leaves instead of per-leaf specifics, and leaf specifics are NOT
re-propagated leaf-to-leaf.

1. Steady state: L4 ECMPs traffic for L1's prefix across S1..Sn. Fine.
2. Link **L1–S1 fails.** L1 is still reachable via S2..Sn.
3. But S1 **keeps the summary valid** (S1 is still up and reachable), so S1 keeps
   advertising the summary to all leaves. No specific withdrawal is generated.
4. L4 has no signal that anything changed. It keeps ECMPing ~1/n of L1's traffic to
   S1. S1 has no specific route to L1's prefix → **drops it.** Blackhole for ~1/n of
   the flows to L1.
   [ipSpace mechanism quote](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/):
   "L4 will (on average) send 50% of its traffic for L1 toward S1 … where the traffic
   will be dropped because S1 has no route for prefixes advertised by L1."

### A.3 Exact blast set (get this RIGHT in the oracle)
- **D6**: the summarization config edit (a route-aggregation/policy change). On its
  own, *before any failure*, D1/D2/D3 are essentially 0 — it even looks like an
  improvement (smaller tables). This is the trap.
- **Conditional D3** (only after the second event — a leaf–spine link failure):
  partial blackhole for the leaves behind the failed link, fraction ≈ 1/n of their
  inbound traffic per failed uplink.
- **D2 lies**: on a remote leaf, the *summary* prefix remains present and "best,"
  even though a subset of addresses inside it is unreachable. A naive D2 (prefix
  presence) check shows NO loss — only D3 (traceroute → blackhole/NO_ROUTE for the
  specific dst) catches it.
- **D1 = 0**: no session changes.

### A.4 The two-snapshot scenario (recommended build)
- Snapshot A: fabric WITHOUT summarization (specifics everywhere), one leaf–spine
  link down → traffic correctly avoids the dead path; D3 clean.
- Snapshot B: SAME link down, but WITH summarization configured → traceroute from a
  remote leaf to a dst behind the affected leaf returns blackhole/NO_ROUTE via the
  summarizing spine, while the summary still shows present in RIB.
- The model under test is shown the *summarization change* and the topology; correct
  answer enumerates the conditional D3 blast and notes D2 presence is misleading.
Batfish modellability: **HIGH** — this is a clean deterministic forwarding diff.

### A.5 The fix operators actually use (so authors recognize "good" configs)
Either (a) don't summarize the underlay at all — what Meta/Google/most CLOS shops do
([ipSpace](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/));
or (b) auto-disaggregation / negative-route ("hole-punch") schemes that re-advertise
the specific for the failed component so traffic stops taking the summary.
[draft-heitz-idr-msdc-bgp-aggregation](https://datatracker.ietf.org/doc/html/draft-heitz-idr-msdc-bgp-aggregation-00),
[draft-chen-isis-black-hole-avoid](https://datatracker.ietf.org/doc/draft-chen-isis-black-hole-avoid/).
A scenario can test recognition that an aggregation config *without* a disaggregation
mechanism is unsafe in a Clos.

### A.6 Why this is NOT redundant with generic "summary blackhole"
The generic enterprise summarization blackhole (a summary advertised toward the core
while a component is down) exists everywhere. The *Clos-specific* sharpening is the
**"exactly one path per Tier-1 to each server"** property + **ECMP fan-out**: the
blackhole is a *fraction* (1/n) of traffic, not all of it, so it presents as partial
packet loss / "some flows fail" — the hardest signature to diagnose and a distinct
test from total loss.

---

## Part B — ECMP / multipath collapse (silent capacity & resilience loss)

### B.1 The requirement
RFC 7938 §6.2: BGP "must support load-sharing over … paths" with "multipath relax" /
"multipath multiple-AS" (eBGP multipath across *different* neighbor ASNs — required
because in the per-tier-ASN scheme equal paths arrive with different AS_PATHs). §6.1:
ECMP fan-out scales with radix (e.g., fan-out 32 for 64-port devices).
[RFC 7938 §6](https://datatracker.ietf.org/doc/html/rfc7938)

### B.2 The safe-looking changes that collapse it
1. **`maximum-paths` reverts to default 1** (or a template ships it as 1). Multipath
   off → only the single best path installs.
2. **`bestpath as-path multipath-relax` removed.** Now equal-cost paths with differing
   AS_PATHs no longer qualify as multipath → collapse to one.
3. **`additional-paths send` removed on a spine/RR** (overlay/anycast). The RR
   advertises only its single best path; clients lose path diversity even though
   multiple equal paths exist.
   [ipSpace add-path](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/),
   [RFC 7911].

### B.3 Exact blast set (the "looks identical" trap)
- **D1 = 0** (sessions unchanged), **D2 = 0** (every prefix still present and best via
  *some* path). A presence/session-only review passes it clean.
- **D5**: redundancy collapses N→1. The hot backup that ECMP provided is gone; the
  next single link failure now forces a reconverge (and a drop window) where before it
  was absorbed instantly.
- **D7**: forwarding for the affected prefixes homes to a single next-hop instead of
  N; for **anycast** prefixes, all traffic now lands on ONE instance instead of being
  balanced — a capacity cliff for that service.
- **D8 (effective)**: bisection capacity for affected prefixes drops by the ECMP
  factor (e.g., /32 of capacity if fan-out was 32). No counter exceeds a hard limit at
  rest, but headroom is gone.

### B.4 Batfish modellability
**GOOD.** Batfish exposes the installed best/multipath set per prefix. Diff pre/post:
the next-hop set for affected prefixes shrinks from N to 1 — directly observable as
D5/D7. What Batfish does NOT capture: runtime hash distribution, anycast instance
selection, and the *future* failure that the lost backup would have covered (that is a
two-snapshot "now fail a link" follow-up). Score the next-hop-count collapse as the
oracle.

### B.5 Anycast amplifier
DC anycast (anycast services, anycast gateways) is advertised from many VTEPs/hosts
and *depends* on ECMP + add-path to balance.
[Anycast in the DC](https://www.dnzydn.com/2023/08/04/anycast-inside-the-data-centers/).
So an ECMP/add-path collapse converts an N-way-balanced anycast service into a
single-instance hotspot — the blast is a *service* (capacity/latency) impact, not a
reachability loss, which maps to D7 + effective-D8 and tests whether a model reasons
about capacity, not just reachability.

---

## Part C — Author checklist: getting the blast set exactly right

For a summarization scenario, the correct answer MUST:
- report **D1=0, D2=0** at the moment of the change (no loss yet — the common LLM
  error is to claim immediate prefix loss);
- identify the **conditional** D3 that appears only on a subsequent leaf–spine link
  failure;
- note the **partial** (≈1/n) nature of the loss under ECMP, and that the summary
  remains *present* in RIB (D2 is a misleading signal).

For an ECMP/multipath-collapse scenario, the correct answer MUST:
- report **D1=0, D2=0** (the trap);
- report **D5 (N→1)** and **D7 (next-hop set shrinks; anycast homes to one)**;
- note no reachability loss *now*, but lost resilience to the *next* failure.

Common LLM failure modes these scenarios target (cf.
`../batfish/blast_radius_patterns.md` §LLM Failure Modes):
- over-counting D1 (claiming sessions drop for an attribute/policy/multipath change —
  they do NOT);
- under-counting D2/D3 specifics (vague "some prefixes may be affected");
- missing D7/D5 entirely (forwarding/redundancy changes are nearly never predicted);
- missing the *conditional* / second-order nature (treating the change as immediately
  harmful or immediately harmless instead of "harmless until the next failure").

---

## References
- [RFC 7938 — Use of BGP for Routing in Large-Scale Data Centers (§3.2.2, §5.2.3, §6)](https://datatracker.ietf.org/doc/html/rfc7938)
- [RFC 7911 — Advertisement of Multiple Paths in BGP](https://datatracker.ietf.org/doc/html/rfc7911)
- [ipSpace — Avoid summarization in leaf-and-spine](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/)
- [ipSpace — BGP add-path / multipath](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/)
- [Anycast inside the data centers](https://www.dnzydn.com/2023/08/04/anycast-inside-the-data-centers/)
- [draft-heitz-idr-msdc-bgp-aggregation — aggregating BGP routes in MSDCs](https://datatracker.ietf.org/doc/html/draft-heitz-idr-msdc-bgp-aggregation-00)
- [draft-chen-isis-black-hole-avoid — avoiding blackholes for aggregation](https://datatracker.ietf.org/doc/draft-chen-isis-black-hole-avoid/)
- Cross-refs (internal): `./hyperscaler_fabric_design.md`,
  `./hyperscaler_dc_failure_modes.md`, `../batfish/blast_radius_patterns.md`,
  `../rfcs/evpn_vxlan_dc.md`.
