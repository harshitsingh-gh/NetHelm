# Microloops and Transient Black Holes During Convergence

## What Is a Microloop?
A microloop is a transient routing loop that forms during network convergence — after a topology change (link failure or recovery) but before all routers have updated their forwarding tables. During this window, different routers have inconsistent views of the network and may forward packets in a circle.

**Key property**: Microloops are transient (seconds to minutes) and self-resolving once convergence completes. But they cause packet loss and high latency during the convergence window.

## How Microloops Form (OSPF Example)
**Topology**: R1 — R2 — R3 — R4 (linear, each link cost 1)
**Destination**: D reachable via R4
**Failure**: Link R3-R4 fails

**Convergence sequence** (assuming R2 converges faster than R1):
1. R3 detects R3-R4 failure immediately (directly connected)
2. R3 updates its forwarding: D is now via R2 (cost 3)
3. R2 receives LSA from R3; converges; updates: D is now via R2 → R3 → R4 (old) or directly...
   - Wait: R2's new best path to D: R2→R3→R2... if R3 now points to R2 for D and R2 points to R3 for D → LOOP

**Specific condition**: After R3-R4 fails:
- R3 knows D is unreachable via R4; best alternate is via R2 (cost 3: R3→R2→R1→R4 is 4; wait, depends on topology)
- R2 hasn't yet received R3's LSA; R2 still thinks D is via R3 (cost 2)
- Traffic arrives at R2 destined for D → R2 forwards to R3
- R3 just updated: R3 now forwards D traffic to R2
- Loop: R2→R3→R2→R3...
- Duration: until R2 converges (receives and processes R3's LSA + recomputes SPF)

## Blast Radius of Microloops
- **D3 (Reachability)**: Transient packet loss for ALL traffic flowing through the affected segment
- **D7 (Forwarding)**: Forwarding paths change and may include a loop
- **Duration**: typically 1–10 seconds (SPF convergence time)
- **Detection**: Hard — routing tables look correct before and after; the loop only exists during convergence

## Loop-Free Alternates (LFA — RFC 5286)
LFA pre-computes backup next-hops that are guaranteed to be loop-free during the convergence window.

**LFA condition** (for pre-existing backup path from R2 to D via backup neighbor N):
`dist(N, D) < dist(N, R2) + dist(R2, D)` (N is closer to D than it is to R2)

If this condition holds, traffic can be immediately forwarded via N when the primary path fails, bypassing the convergence loop.

**Config (IOS)**:
```
router ospf 1
 fast-reroute per-prefix enable area 0 prefix-priority critical
 fast-reroute per-prefix tie-breaking default
```

**Remote LFA (rLFA — RFC 7490)**: extends LFA to cases where no topological LFA exists by using a tunnel to a "PQ node" that is guaranteed loop-free.

## Microloop Avoidance (RFC 8333)
Introduces controlled convergence delays to prevent microloops:
1. Router A detects failure and updates its RIB
2. Before distributing the update, A waits a configurable delay
3. During this delay, A continues forwarding via the old path (which may be suboptimal but not a loop)
4. After the delay, A distributes the updated LSA
5. All routers converge together, preventing the asymmetric convergence window

**Trade-off**: Slower convergence in exchange for no microloops.

## Transient Black Holes (Not Loops — Suboptimal Convergence)
Similar to microloops, but instead of a loop, the packet reaches a router that has already removed the route and has no alternate — the packet is dropped.

**Scenario**: R1→R2→R3 (R3 is the exit). R2 receives LSA update (R3-side link failed). R2 immediately withdraws D from its RIB. R1 hasn't converged yet — R1 still points to R2 for D. Traffic arrives at R2 → R2 has no route to D → DROP.

This is a transient black hole. Duration: until R1 converges (receives LSA and recomputes).

**Blast radius**: D3 (reachability loss), but transient. Often manifests as unexplained packet drops during maintenance windows.

## FRR-Square Lab Microloop Testing
In the 4-router FRR-square topology (R1-R2, R1-R3, R2-R4, R3-R4 in a diamond), microloops are theoretically possible if:
- One of the cross links fails
- SPF timer configurations differ between nodes
- BFD is enabled with short timers

**NetHELM scenario**: Trigger controlled interface failure; capture Batfish pre/post snapshots; ask LLM to identify which paths might experience transient inconsistency during convergence.

**Batfish limitation**: Batfish models steady-state routing, not transient convergence states. Batfish can tell you pre-failure and post-failure routes, but NOT what happens during convergence. Microloop blast radius must be analyzed theoretically or in a live lab with packet capture.

## OSPF Incremental SPF and Partial SPF
Full SPF re-run on every topology change is expensive. Optimizations:
- **iSPF (Incremental SPF)**: Only recomputes affected portions of the SPF tree. Reduces CPU but may introduce convergence inconsistencies.
- **PRC (Partial Route Calculation)**: For leaf changes (stub networks), only the affected leaf is recomputed. Much faster than full SPF.

**Convergence timers (IOS)**:
```
router ospf 1
 timers throttle spf 50 200 5000
 ! SPF delay: initial 50ms, hold 200ms, max 5000ms
 timers throttle lsa 50 200 5000
 ! LSA delay: same parameters
```

## Practical Blast Radius Estimation for Microloops
For a given OSPF topology, the microloop blast radius during link failure:
1. Identify which router(s) will converge slowest (highest SPF delay + LSA propagation time)
2. Traffic between any pair (src, dst) that previously used the failed link AND passes through a slow-to-converge router is at risk
3. Duration = SPF timer + LSA propagation + FIB update time
4. A complex LSDB (many LSAs) increases SPF time

For NetHELM evaluation: LLMs should at minimum identify WHICH paths are at risk during convergence, even if they can't compute the exact duration.
